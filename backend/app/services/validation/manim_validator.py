"""ManimValidator: static (AST) validation of generated Manim code before it is executed.

This is the first line of defence for untrusted code; the sandbox (services/manim/sandbox.py)
is the second. The validator enforces a controlled subset of Manim + Python.
"""

from __future__ import annotations

import ast
import re

from app.schemas.generation import ManimCode, VisualPlan
from app.schemas.validation import ValidationIssue, ValidationResult

NAME = "manim"
MAX_CODE_CHARS = 20_000

ALLOWED_IMPORTS: dict[str, set[str] | None] = {
    "manim": None,  # `from manim import *` or specific names
    "math": None,
    "numpy": None,
    "tutorly_visuals": None,  # the deterministic Tutorly visual runtime (theme, primitives, Stage)
}

# Controlled subset of Manim (mobjects, animations, helpers).
MANIM_CALLS: frozenset[str] = frozenset(
    {
        # mobjects
        "Text", "MarkupText", "Paragraph", "MathTex", "Tex", "VGroup", "Group", "Circle", "Square", "Rectangle",
        "RoundedRectangle", "Line", "DashedLine", "Arrow", "DoubleArrow", "CurvedArrow", "Vector", "Dot", "Brace",
        "BraceLabel", "SurroundingRectangle", "BackgroundRectangle", "Cross", "Underline", "Polygon", "Triangle",
        "RegularPolygon", "Ellipse", "Arc", "Annulus", "NumberLine", "Axes", "NumberPlane", "DecimalNumber",
        "Integer", "Variable", "Table", "MathTable", "IntegerTable", "Graph", "DiGraph", "Star",
        # animations
        "Create", "Uncreate", "Write", "Unwrite", "DrawBorderThenFill", "FadeIn", "FadeOut", "Transform",
        "ReplacementTransform", "TransformFromCopy", "TransformMatchingTex", "TransformMatchingShapes",
        "Indicate", "Circumscribe", "Flash", "Wiggle", "FocusOn", "ShowPassingFlash", "GrowFromCenter",
        "GrowFromEdge", "GrowArrow", "SpinInFromNothing", "LaggedStart", "LaggedStartMap", "AnimationGroup",
        "Succession", "Wait", "MoveToTarget", "Rotate", "Swap", "CyclicReplace", "FadeTransform",
        "ApplyWave", "AddTextLetterByLetter", "ChangeDecimalToValue",
        # helpers
        "interpolate_color", "color_gradient", "ManimColor", "always_redraw", "ValueTracker",
        # 3D (stereometry scenes: ThreeDScene)
        "Sphere", "Cube", "Prism", "Cylinder", "Cone", "Dot3D", "Line3D", "Arrow3D", "Surface", "ThreeDAxes",
        "Polyhedron", "Tetrahedron", "Octahedron",
        # Tutorly visual runtime
        "Stage",
        "Stage3D",
        "Board",
    }
)

SAFE_BUILTINS: frozenset[str] = frozenset(
    {
        "range", "len", "enumerate", "zip", "list", "dict", "tuple", "set", "str", "int", "float", "min", "max",
        "abs", "round", "sum", "sorted", "reversed", "isinstance", "any", "all", "map", "super", "print",
    }
)

FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "exec", "eval", "compile", "open", "__import__", "globals", "locals", "vars", "getattr", "setattr",
        "delattr", "input", "breakpoint", "exit", "quit", "help", "memoryview", "os", "sys", "subprocess",
        "socket", "shutil", "pathlib", "Path", "importlib", "builtins", "config", "tempconfig", "type",
        "object", "classmethod", "staticmethod", "property", "dir", "id", "hash",
    }
)

FORBIDDEN_ATTRS: frozenset[str] = frozenset(
    {
        "system", "popen", "spawn", "remove", "unlink", "rmdir", "rmtree", "write_text", "write_bytes",
        "read_text", "read_bytes", "load", "loads", "save", "savefig", "tofile", "fromfile", "chdir",
        "environ", "getenv", "putenv", "kill", "fork", "connect", "urlopen", "renderer", "file_writer",
    }
)

SCENE_BASES = {"Scene", "MovingCameraScene", "ThreeDScene"}
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?|#[0-9a-fA-F]{3}")
_EVENT_MARK = re.compile(r"#\s*EVENT:\s*([A-Za-z0-9_\-]+)", re.IGNORECASE)


class ManimValidator:
    def validate(self, manim: ManimCode, plan: VisualPlan | None = None) -> ValidationResult:
        issues: list[ValidationIssue] = []
        code = manim.code

        if len(code) > MAX_CODE_CHARS:
            issues.append(ValidationIssue(code="CODE_TOO_LONG", message=f"code exceeds {MAX_CODE_CHARS} characters"))
            return ValidationResult.build(NAME, f"manim:{manim.scene_id}", issues)

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            issues.append(
                ValidationIssue(code="SYNTAX_ERROR", message=f"line {exc.lineno}: {exc.msg}", location=f"line {exc.lineno}")
            )
            return ValidationResult.build(NAME, f"manim:{manim.scene_id}", issues)

        defined: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, (ast.Name)) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, ast.arg):
                defined.add(node.arg)

        scene_classes: list[ast.ClassDef] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                if bases & SCENE_BASES:
                    scene_classes.append(node)

        for node in ast.walk(tree):
            loc = f"line {getattr(node, 'lineno', '?')}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                        issues.append(ValidationIssue(code="FORBIDDEN_IMPORT", message=f"import {alias.name}", location=loc))
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod not in ALLOWED_IMPORTS or node.level:
                    issues.append(
                        ValidationIssue(code="FORBIDDEN_IMPORT", message=f"from {node.module} import ...", location=loc)
                    )
            elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                issues.append(ValidationIssue(code="FORBIDDEN_NAME", message=f"use of '{node.id}'", location=loc))
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("_"):
                    issues.append(
                        ValidationIssue(code="PRIVATE_ATTRIBUTE", message=f"access to '{node.attr}'", location=loc)
                    )
                elif node.attr in FORBIDDEN_ATTRS:
                    issues.append(
                        ValidationIssue(code="FORBIDDEN_ATTRIBUTE", message=f"access to '.{node.attr}'", location=loc)
                    )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                fn = node.func.id
                if fn not in MANIM_CALLS and fn not in SAFE_BUILTINS and fn not in defined and fn not in FORBIDDEN_NAMES:
                    issues.append(
                        ValidationIssue(
                            code="DISALLOWED_CALL",
                            message=f"'{fn}(...)' is outside the allowed Manim subset",
                            location=loc,
                        )
                    )
            elif isinstance(node, (ast.While, ast.AsyncFunctionDef, ast.Await, ast.Global, ast.Nonlocal)):
                issues.append(
                    ValidationIssue(code="DISALLOWED_SYNTAX", message=f"{type(node).__name__} is not allowed", location=loc)
                )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _HEX_COLOR.fullmatch(node.value.strip()):
                issues.append(ValidationIssue(code="ARBITRARY_COLOR", message=f"literal colour {node.value!r}; use theme colours", location=loc))
            elif isinstance(node, ast.keyword) and node.arg in ("font", "font_family"):
                issues.append(ValidationIssue(code="ARBITRARY_FONT", message="fonts are owned by the Tutorly theme", location=loc))
            elif isinstance(node, ast.With):
                issues.append(ValidationIssue(code="DISALLOWED_SYNTAX", message="'with' is not allowed", location=loc))

        if plan is not None and plan.layout == "space_3d" and scene_classes:
            bases = {b.id for b in scene_classes[0].bases if isinstance(b, ast.Name)}
            if "ThreeDScene" not in bases:
                issues.append(
                    ValidationIssue(
                        code="NEEDS_3D_SCENE",
                        message="this is a 3D (stereometry) plan: subclass ThreeDScene, draw the solids in 3D "
                        "(Sphere, Cube, Polyhedron, Line3D, Dot3D ...) and set the camera with set_camera_orientation",
                    )
                )
        if len(scene_classes) != 1:
            issues.append(
                ValidationIssue(
                    code="SCENE_CLASS_COUNT",
                    message=f"expected exactly one Scene subclass, found {len(scene_classes)}",
                )
            )
        else:
            cls = scene_classes[0]
            if cls.name != manim.class_name:
                issues.append(
                    ValidationIssue(
                        code="CLASS_NAME_MISMATCH",
                        message=f"class is '{cls.name}' but class_name says '{manim.class_name}'",
                    )
                )
            if not any(isinstance(n, ast.FunctionDef) and n.name == "construct" for n in cls.body):
                issues.append(ValidationIssue(code="NO_CONSTRUCT", message="Scene subclass has no construct()"))

        # Narration/visual synchronisation markers
        missing: list[str] = []
        if plan is not None:
            marked = {m.lower() for m in _EVENT_MARK.findall(code)}
            missing = [e.id for e in plan.events if e.id.lower() not in marked]
            if missing:
                issues.append(
                    ValidationIssue(
                        code="EVENT_MARKERS_MISSING",
                        message=f"no '# EVENT: <id>' marker for visual events: {', '.join(missing)}",
                        severity="warning",
                    )
                )

        return ValidationResult.build(NAME, f"manim:{manim.scene_id}", issues, missing_events=missing)

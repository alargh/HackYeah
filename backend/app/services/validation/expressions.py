"""Safe parsing/evaluation of mathematical expressions produced by the LLM.

`sympy.parse_expr` uses `eval` internally, so LLM text must never reach it unchecked:
- characters are whitelisted (no quotes, no attribute access, no keywords, no dunders);
- parsing uses a RESTRICTED namespace (only the functions below), never SymPy's full namespace
  (which contains e.g. `preview`/`plot` that run external programs); every other identifier
  becomes a plain Symbol (or undefined Function when called), which is harmless;
- combinatorial arguments and exponents are bounded before evaluation.

Supports integers/rationals, complex numbers (I, exp, ...), trig/log, Sum/Product and symbolic results.
"""

from __future__ import annotations

import keyword
import re
from typing import Mapping

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    factorial_notation,
    parse_expr,
    standard_transformations,
)

MAX_EXPR_LEN = 400
MAX_COMBINATORIAL_ARG = 5000

class ExpressionError(ValueError):
    pass


def _bounded(fn):
    """Function calls are evaluated eagerly by parse_expr, so bound arguments *before* calling."""

    def call(*args):
        for a in args:
            a = sympy.sympify(a)
            if a.is_number and abs(a) > MAX_COMBINATORIAL_ARG:
                raise ExpressionError(f"argument {a} too large for {fn.__name__}")
        return fn(*args)

    return call


class Stirling2(sympy.Function):
    """Stirling number of the second kind S(n, k): ways to split n labelled items into k non-empty groups.
    Symbolic until both arguments are integers (then evaluated exactly)."""

    @classmethod
    def eval(cls, n, k):
        if n.is_Integer and k.is_Integer:
            if max(abs(n), abs(k)) > MAX_COMBINATORIAL_ARG:
                raise ExpressionError("argument too large for Stirling2")
            if n < 0 or k < 0:
                return sympy.Integer(0)
            from sympy.functions.combinatorial.numbers import stirling

            return sympy.Integer(stirling(int(n), int(k), kind=2))
        return None


_FUNCTIONS: dict[str, object] = {
    "Stirling2": Stirling2,
    "stirling2": Stirling2,
    "S2": Stirling2,
    "factorial": _bounded(sympy.factorial),
    "binomial": _bounded(sympy.binomial),
    "C": _bounded(sympy.binomial),  # C(n, k)
    "P": _bounded(sympy.ff),  # P(n, k) = n!/(n-k)!
    "ff": _bounded(sympy.ff),
    "rf": _bounded(sympy.rf),
    "sqrt": sympy.sqrt,
    "gcd": sympy.gcd,
    "lcm": sympy.lcm,
    "floor": sympy.floor,
    "ceiling": sympy.ceiling,
    "Abs": sympy.Abs,
    "abs": sympy.Abs,
    "Rational": sympy.Rational,
    "fibonacci": _bounded(sympy.fibonacci),
    "catalan": _bounded(sympy.catalan),
    "pi": sympy.pi,
    "E": sympy.E,
    "I": sympy.I,
    "oo": sympy.oo,
    "exp": sympy.exp,
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "atan": sympy.atan,
    "asin": sympy.asin,
    "acos": sympy.acos,
    "arctan": sympy.atan,
    "arcsin": sympy.asin,
    "arccos": sympy.acos,
    "cot": sympy.cot,
    "log": sympy.log,
    "ln": sympy.log,
    "re": sympy.re,
    "im": sympy.im,
    "conjugate": sympy.conjugate,
    "arg": sympy.arg,
    "Sum": sympy.Sum,
    "Product": sympy.Product,
    "Tuple": sympy.Tuple,
    "Mod": sympy.Mod,
    "Max": sympy.Max,
    "Min": sympy.Min,
}

# Names parse_expr's own transformations emit (numbers, auto-symbols).
_PARSER_NAMES: dict[str, object] = {
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
    "Symbol": sympy.Symbol,
    "Function": sympy.Function,
    # evaluate=False rewrites operators into these constructors
    "Add": sympy.Add,
    "Mul": sympy.Mul,
    "Pow": sympy.Pow,
}
MAX_IDENT_LEN = 24
SIMPLIFY_MAX_OPS = 200

_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z_+\-*/^()!.,\s]+$")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_BAD_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")
_TRANSFORMS = standard_transformations + (factorial_notation, convert_xor)


def normalize(text: str) -> str:
    s = text.strip()
    for a, b in (("×", "*"), ("·", "*"), ("⋅", "*"), ("−", "-"), ("–", "-"), ("÷", "/"), ("\\cdot", "*"), ("\\times", "*")):
        s = s.replace(a, b)
    # Drop a trailing "= value" if the model wrote "5! - 2*4! = 72".
    if "=" in s:
        s = s.split("=")[0].strip()
    return s


def _walk_bounds(expr: sympy.Basic) -> None:
    for node in sympy.preorder_traversal(expr):
        if isinstance(node, (sympy.factorial, sympy.binomial, sympy.ff, sympy.rf, sympy.fibonacci, sympy.catalan)):
            for arg in node.args:
                if arg.is_number and abs(arg) > MAX_COMBINATORIAL_ARG:
                    raise ExpressionError(f"argument {arg} too large for {node.func.__name__}")
        if isinstance(node, sympy.Pow) and node.exp.is_number and abs(node.exp) > 1000:
            raise ExpressionError("exponent too large")


def parse_safe(text: str, names: Mapping[str, sympy.Expr] | None = None) -> sympy.Expr:
    """Parse `text` into a SymPy expression, allowing only whitelisted identifiers.

    `names` binds identifiers (e.g. earlier step result names) to already-evaluated values.
    """
    names = dict(names or {})
    s = normalize(text)
    if not s:
        raise ExpressionError("empty expression")
    if len(s) > MAX_EXPR_LEN:
        raise ExpressionError("expression too long")
    if not _ALLOWED_CHARS.match(s):
        raise ExpressionError(f"disallowed characters in expression: {text!r}")
    if _BAD_DOT.search(s):
        raise ExpressionError("attribute access is not allowed in expressions")
    for ident in _IDENT.findall(s):
        if ident in _FUNCTIONS or ident in names:
            continue
        if keyword.iskeyword(ident) or ident.startswith("_") or len(ident) > MAX_IDENT_LEN or ident in _PARSER_NAMES:
            raise ExpressionError(f"identifier '{ident}' is not allowed")
        # anything else becomes a free Symbol / undefined Function

    local_dict: dict[str, object] = {**_FUNCTIONS, **names}
    global_dict: dict[str, object] = {"__builtins__": {}, **_PARSER_NAMES}
    try:
        expr = parse_expr(s, local_dict=local_dict, global_dict=global_dict, transformations=_TRANSFORMS, evaluate=False)
    except Exception as exc:  # SyntaxError, TokenError, TypeError...
        raise ExpressionError(f"cannot parse {text!r}: {exc}") from exc
    if not isinstance(expr, sympy.Basic):
        expr = sympy.sympify(expr)
    _walk_bounds(expr)
    return expr


def _simplify(e: sympy.Expr) -> sympy.Expr:
    if isinstance(e, sympy.Tuple):  # several answers, e.g. (V, S)
        return sympy.Tuple(*(_simplify(x) for x in e))
    return sympy.simplify(e) if sympy.count_ops(e) <= SIMPLIFY_MAX_OPS else e


def evaluate(text: str, names: Mapping[str, sympy.Expr] | None = None, numeric: bool = False) -> sympy.Expr:
    """Evaluate `text`. Symbolic results are allowed unless `numeric=True`."""
    expr = parse_safe(text, names)
    try:
        value = _simplify(expr.doit())
    except ExpressionError:
        raise
    except Exception as exc:
        raise ExpressionError(f"cannot evaluate {text!r}: {exc}") from exc
    if numeric and value.free_symbols:
        raise ExpressionError(f"expression {text!r} is not fully numeric")
    return value


def is_numeric(value: sympy.Expr) -> bool:
    return not getattr(value, "free_symbols", set())


def _plain_symbols(e):
    """Match symbols by name: 'a' from a solution and a positive 'a' from exact geometry are the same side."""
    syms = getattr(e, "free_symbols", set())
    return e.xreplace({s: sympy.Symbol(s.name) for s in syms}) if syms else e


_PROBES = (2, 3, 4, 5, 7)


def _probes(a, b) -> list[dict]:
    """Integer assignments for the free symbols (n, k, a, ...) used to compare formulas by value."""
    syms = sorted((getattr(a, "free_symbols", set()) | getattr(b, "free_symbols", set())), key=lambda s: s.name)
    if not syms or len(syms) > 3:
        return []
    out = []
    for i, v in enumerate(_PROBES):
        out.append({s: sympy.Integer(v + 2 * j + (i % 2) * j) for j, s in enumerate(syms)})
    return out


def counterexample(a, b) -> str | None:
    """'for k=3: 7 vs 13' when two formulas differ at some integer values (None if no difference is found)."""
    a, b = _plain_symbols(a), _plain_symbols(b)
    for sub in _probes(a, b):
        try:
            va, vb = sympy.simplify(a.subs(sub).doit()), sympy.simplify(b.subs(sub).doit())
        except Exception:  # noqa: BLE001
            continue
        if va.free_symbols or vb.free_symbols:
            continue
        if abs(complex(sympy.N(va - vb, 30))) > 1e-9:
            where = ", ".join(f"{s}={v}" for s, v in sub.items())
            return f"for {where}: {va} vs {vb}"
    return None


def _equal_by_values(a, b) -> bool:
    """Formulas with integer parameters (n, k) that SymPy cannot simplify into each other (e.g. Stirling
    numbers vs binomials): equal when they agree at every probe."""
    probes = _probes(a, b)
    checked = 0
    for sub in probes:
        try:
            va, vb = sympy.simplify(a.subs(sub).doit()), sympy.simplify(b.subs(sub).doit())
        except Exception:  # noqa: BLE001
            return False
        if va.free_symbols or vb.free_symbols:
            return False
        if abs(complex(sympy.N(va - vb, 30))) > 1e-9:
            return False
        checked += 1
    return checked >= 4


def equal(a: sympy.Expr, b: sympy.Expr) -> bool:
    a, b = _plain_symbols(a), _plain_symbols(b)
    if isinstance(a, (sympy.Tuple, tuple)) or isinstance(b, (sympy.Tuple, tuple)):
        a_t = list(a) if isinstance(a, (sympy.Tuple, tuple)) else [a]
        b_t = list(b) if isinstance(b, (sympy.Tuple, tuple)) else [b]
        return len(a_t) == len(b_t) and all(equal(x, y) for x, y in zip(a_t, b_t))
    try:
        diff = a - b
        if is_numeric(diff):
            if sympy.simplify(diff) == 0:
                return True
            return bool(abs(complex(sympy.N(diff, 30))) < 1e-9)
        if sympy.expand(diff) == 0 or _simplify(diff) == 0:
            return True
        if bool(a.equals(b)):
            return True
        return _equal_by_values(a, b)
    except Exception:
        return False


def to_str(value: sympy.Expr) -> str:
    return str(value)

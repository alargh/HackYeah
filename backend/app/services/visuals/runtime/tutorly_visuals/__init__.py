"""Tutorly visual runtime: deterministic Manim Community building blocks for compiled scenes.

This package is copied into the render sandbox and imported by compiled scene code, so it must only
depend on Manim, SymPy and the standard library (never on the `app` package). Imports are lazy so the
backend can use the pure `geometry` module without loading Manim.
"""

__all__ = ["Board", "ROLE_COLORS", "Stage", "Stage3D"]


def __getattr__(name):
    if name == "Stage":
        from .stage import Stage

        return Stage
    if name == "Board":
        from .board import Board

        return Board
    if name == "Stage3D":
        from .stage3d import Stage3D

        return Stage3D
    if name == "ROLE_COLORS":
        from .theme import ROLE_COLORS

        return ROLE_COLORS
    raise AttributeError(name)

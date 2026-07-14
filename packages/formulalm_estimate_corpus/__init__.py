"""Provenance-first local estimate candidates for FormulaLM.

This package prepares integrity-signed, explicitly unapproved candidate views.
It does not authorize training, train a model, or replace the deterministic
Decimal estimate calculator.
"""

from .pipeline import (
    LocalCandidateBuildResult,
    build_local_candidate,
    verify_local_candidate,
)

__all__ = [
    "LocalCandidateBuildResult",
    "build_local_candidate",
    "verify_local_candidate",
]

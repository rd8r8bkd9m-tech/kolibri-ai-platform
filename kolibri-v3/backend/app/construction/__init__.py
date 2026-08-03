"""Construction vertical module for Kolibri V3.

This module provides professional construction agents that collaborate
to produce estimates, documents, and other construction artifacts.

It plugs into Platform Core's durable run, A2A, and AG-UI infrastructure
without placing construction-specific entities in Core.
"""

from .registry import (
    ConstructionAgentRegistry,
    get_construction_registry,
    CONSTRUCTION_MODULE_ID,
)

__all__ = [
    "ConstructionAgentRegistry",
    "get_construction_registry",
    "CONSTRUCTION_MODULE_ID",
]

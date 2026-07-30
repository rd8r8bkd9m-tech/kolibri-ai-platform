"""Tenant-scoped Kolibri V3 Product Chat.

The package deliberately has no eager router import.  Runtime modules import
``chat.service`` while the router imports the execution adapter, which in turn
imports the direct model runtime.  Importing the router here made otherwise
independent authentication tests depend on import order and could expose a
partially initialized runtime module.
"""

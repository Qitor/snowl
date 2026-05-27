"""Backward-compat re-export of ChatModelClient from core.

The canonical definition now lives in ``snowl.core.protocols``.
This module re-exports it so that existing ``from snowl.model.base import ChatModelClient``
and ``from snowl.model import ChatModelClient`` continue to work.
"""

from snowl.core.protocols import ChatModelClient  # noqa: F401

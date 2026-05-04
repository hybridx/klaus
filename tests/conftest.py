"""Shared fixtures for the klaus test suite."""

from __future__ import annotations

import pytest

from klaus.memory.tree import MemoryTree


@pytest.fixture()
def tree() -> MemoryTree:
    """Fresh memory tree with default branches."""
    return MemoryTree()

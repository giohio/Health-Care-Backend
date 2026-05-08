"""Compatibility shim for projects that import ``uuid_extension``.

This local package provides a minimal UUID7-like API without external fetches.
"""

from uuid import UUID, uuid4

# Keep the public type name used across services.
UUID7 = UUID


def uuid7() -> UUID:
    """Return a UUID value.

    Uses UUID4 as a pragmatic fallback when UUID7 generator is unavailable.
    """

    return uuid4()


__all__ = ["UUID7", "uuid7"]
"""Target drivers. One per system type, all with the same operations."""
from __future__ import annotations

from ..config import Settings
from ..models import Target
from .base import Driver, DriverError

__all__ = ["Driver", "DriverError", "get_driver"]


def get_driver(target: Target, settings: Settings) -> Driver:
    """Create the driver for a target. Imports are lazy, so a missing optional
    library (pyrfc, playwright, google-auth) only matters for its own target type."""
    if target.type == "abap":
        from .abap import AbapDriver as cls
    elif target.type == "java_nwa":
        from .java_nwa import JavaNwaDriver as cls
    elif target.type == "cloudrun":
        from .cloudrun import CloudRunDriver as cls
    elif target.type == "fake":
        from .fake import FakeDriver as cls
    else:
        raise DriverError(f"target {target.name!r}: unknown type {target.type!r}")
    return cls(target, settings)

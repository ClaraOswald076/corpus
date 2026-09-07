"""Timezone helpers for values read back from SQLite."""
from datetime import datetime, timezone


def as_aware_utc(dt: datetime) -> datetime:
    """SQLite storage drops tzinfo, so cross-session reads come back naive.
    Treat naive values as UTC before doing arithmetic with aware now()."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

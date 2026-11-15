"""Shared test setup."""

try:  # pycares starts a daemon shutdown thread lazily; start it before the
    # HA test harness snapshots threads so it isn't reported as lingering.
    import pycares

    pycares.Channel()
except Exception:  # noqa: BLE001
    pass

"""Errors a command reports to the user."""


class UsageError(Exception):
    """A bad argument: reported as `dockops: MESSAGE` with exit status 2."""


class NotFound(Exception):
    """Nothing matches what was asked for: reported as `dockops: MESSAGE` with exit status 1."""

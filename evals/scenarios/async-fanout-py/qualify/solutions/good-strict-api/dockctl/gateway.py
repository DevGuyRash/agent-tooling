"""Client for the dock gateway's HTTP API (see docs/gateway-api.md)."""

import json
import os
import urllib.error
import urllib.request

DEFAULT_GATEWAY = "http://127.0.0.1:8470"


class GatewayError(Exception):
    """The gateway answered with an error status, or could not be reached.

    `status` is the HTTP status code when the gateway answered, None when it
    could not be reached at all.
    """

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoAnswer(GatewayError):
    """The gateway did not answer within the time allowed."""


def gateway_url(override=None):
    """The gateway's base URL: the --gateway option, $DOCKCTL_GATEWAY, or the default."""
    return (override or os.environ.get("DOCKCTL_GATEWAY") or DEFAULT_GATEWAY).rstrip("/")


def _get(base, path, *, timeout):
    """GET base+path as JSON; NoAnswer when the gateway is silent for `timeout` seconds (None: as long as
    the gateway takes)."""
    try:
        with urllib.request.urlopen(base + path, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise GatewayError(f"{path}: HTTP {exc.code}", status=exc.code) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise NoAnswer(f"{path}: no answer within {timeout} s") from None
        raise GatewayError(f"cannot reach the gateway at {base}: {exc.reason}") from None
    except TimeoutError:
        raise NoAnswer(f"{path}: no answer within {timeout} s") from None


def list_docks(base, *, timeout):
    """Every dock the gateway knows, as (id, name) pairs, in the gateway's order."""
    data = _get(base, "/v1/docks", timeout=timeout)
    return [(d["id"], d["name"]) for d in data["docks"]]


def dock_status(base, dock_id, *, timeout):
    """A dock's current status, read live from the dock: {"id", "bikes", "free", ...}."""
    return _get(base, f"/v1/docks/{dock_id}/status", timeout=timeout)

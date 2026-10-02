"""Client for the BMS gateway's HTTP API (see docs/bms-gateway.md)."""

import json
import os
import urllib.error
import urllib.request

DEFAULT_GATEWAY = "http://127.0.0.1:8640"


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
    """The gateway's base URL: the --gateway option, $COLDCTL_GATEWAY, or the default."""
    return (override or os.environ.get("COLDCTL_GATEWAY") or DEFAULT_GATEWAY).rstrip("/")


def _get(base, path, timeout=None):
    """GET base+path as JSON. With a timeout, NoAnswer when the gateway is silent that long."""
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


def list_units(base, timeout=None):
    """Every refrigeration unit the gateway knows, as (id, zone) pairs, in the gateway's order."""
    data = _get(base, "/v2/units", timeout)
    return [(u["id"], u["zone"]) for u in data["units"]]


def unit_reading(base, unit_id, timeout=2.0):
    """A unit's current reading, taken live from its controller: {"id", "temp_c", "setpoint_c", "defrost", ...}."""
    return _get(base, f"/v2/units/{unit_id}/reading", timeout)

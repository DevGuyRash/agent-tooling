"""Client for the BMS gateway's HTTP API (see docs/bms-gateway.md)."""

import http.client
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit

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


def unit_reading(base, unit_id, timeout=None):
    """A unit's current reading, taken live from its controller: {"id", "temp_c", "setpoint_c", "defrost", ...}."""
    return _get(base, f"/v2/units/{unit_id}/reading", timeout)


class Session:
    """One keep-alive connection to the gateway, reused for request after request (no new TCP connection and
    no urllib overhead per unit). A request that times out or fails drops the connection; the next one opens
    a fresh one."""

    def __init__(self, base):
        parts = urlsplit(base)
        self.base, self.host, self.port = base, parts.hostname, parts.port or 80
        self.conn = None

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def get(self, path, timeout):
        if self.conn is None:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        else:
            self.conn.timeout = timeout
            if self.conn.sock is not None:
                self.conn.sock.settimeout(timeout)
        try:
            self.conn.request("GET", path)
            resp = self.conn.getresponse()
            body = resp.read()
        except TimeoutError:
            self.close()
            raise NoAnswer(f"{path}: no answer within {timeout} s") from None
        except (OSError, http.client.HTTPException) as exc:
            self.close()
            raise GatewayError(f"cannot reach the gateway at {self.base}: {exc}") from None
        if resp.status != 200:
            raise GatewayError(f"{path}: HTTP {resp.status}", status=resp.status)
        return json.loads(body)

    def unit_reading(self, unit_id, timeout):
        return self.get(f"/v2/units/{unit_id}/reading", timeout)

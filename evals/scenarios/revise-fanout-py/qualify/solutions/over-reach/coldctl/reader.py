"""Reading many units at once, for every command that reads units."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .gateway import GatewayError, NoAnswer, unit_reading

GATEWAY_LIMIT = 16     # requests in progress per client (docs/bms-gateway.md)
NO_ANSWER_AFTER = 2.0  # seconds before a unit counts as not answering


@dataclass(frozen=True)
class Result:
    unit_id: str
    outcome: str          # "read", "no answer", or "failed"
    reading: dict | None  # the reading when outcome is "read"
    status: int | None    # the HTTP status when outcome is "failed" and the gateway answered


def read_one(base, unit_id, timeout=NO_ANSWER_AFTER):
    try:
        return Result(unit_id, "read", unit_reading(base, unit_id, timeout=timeout), None)
    except NoAnswer:
        return Result(unit_id, "no answer", None, None)
    except GatewayError as exc:
        return Result(unit_id, "failed", None, exc.status)


def read_units(base, unit_ids, timeout=NO_ANSWER_AFTER):
    """Results for unit_ids, sorted by unit ID, with at most GATEWAY_LIMIT reads in progress."""
    ids = sorted(set(unit_ids))
    with ThreadPoolExecutor(max_workers=GATEWAY_LIMIT) as pool:
        return list(pool.map(lambda unit_id: read_one(base, unit_id, timeout), ids))

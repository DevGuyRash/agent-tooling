"""Signatures for critical notices, so that a device can tell them from forgeries."""
import hashlib
import hmac
import json


def sign(payload, key):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def verify(payload, signature, key):
    return hmac.compare_digest(sign(payload, key), signature)

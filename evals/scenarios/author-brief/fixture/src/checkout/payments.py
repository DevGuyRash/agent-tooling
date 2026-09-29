from . import config


def charge(db, cache, session_id, amount_cents):
    session = cache.get(session_id) or db.load_session(session_id)
    cache.set(session_id, session, ttl=config.SESSION_CACHE_TTL_S)
    with db.connection(timeout=config.DB_POOL_TIMEOUT_S) as conn:
        order = conn.insert_order(session["cart"], amount_cents)
        return conn.capture_payment(order, timeout=config.PAYMENT_PROVIDER_TIMEOUT_S)

"""Тесты лимитера: скользящее окно на client_id."""

from app.core.rate_limiter import SlidingWindowRateLimiter


def test_allows_requests_within_limit():
    limiter = SlidingWindowRateLimiter(limit_per_minute=2)
    assert limiter.check("user-1") is True
    assert limiter.check("user-1") is True
    assert limiter.check("user-1") is False


def test_clients_are_independent():
    limiter = SlidingWindowRateLimiter(limit_per_minute=1)
    assert limiter.check("a") is True
    assert limiter.check("a") is False
    assert limiter.check("b") is True


def test_window_resets_after_time():
    # Маленькое окно понадобилось бы через публичное API — проверяем логику внутри,
    # подменяя время через прямое добавление записей в очередь.
    limiter = SlidingWindowRateLimiter(limit_per_minute=1)
    assert limiter.check("user-1") is True
    assert limiter.check("user-1") is False
    limiter._hits["user-1"][0] -= 61.0  # старим запись больше окна
    assert limiter.check("user-1") is True
"""Простое лимитирование: скользящее окно запросов в минуту на client_id.

Хранится в памяти процесса — подходит для MVP на одном инстансе Uvicorn.
"""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Ограничивает число принятых запросов в минуту для одного ключа."""

    def __init__(self, limit_per_minute: int):
        self._limit = max(1, limit_per_minute)
        self._window_seconds = 60.0
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """True — запрос можно принять, False — лимит для ключа превышен."""
        now = time.monotonic()
        with self._lock:
            queue = self._hits[key]
            # Выкидываем записи старше окна в 60 секунд
            while queue and now - queue[0] >= self._window_seconds:
                queue.popleft()
            if len(queue) >= self._limit:
                return False
            queue.append(now)
            return True

    def cleanup(self) -> None:
        """Удаляет окна неактивных клиентов (освобождение памяти)."""
        now = time.monotonic()
        with self._lock:
            for key in list(self._hits):
                queue = self._hits[key]
                while queue and now - queue[0] >= self._window_seconds:
                    queue.popleft()
                if not queue:
                    del self._hits[key]
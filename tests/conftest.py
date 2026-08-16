"""Общие фикстуры pytest.

TestClient необходимо использовать как context manager, чтобы FastAPI
отработал lifespan (создание схемы БД, инициализация логгеров).
"""

import os

# Тесты всегда работают в демо-режиме (без реального ключа LLM),
# чтобы не было сетевых вызовов даже если в .env задан LLM_API_KEY.
os.environ["LLM_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client
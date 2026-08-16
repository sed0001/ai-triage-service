"""Настройки приложения: загружаются из переменных окружения / файла .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Параметры конфигурации читаются из .env и системного окружения
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (ProxyAPI, OpenAI-совместимый эндпоинт) ---
    llm_api_key: str = ""  # задаётся через .env, в коде не хранится
    llm_base_url: str = "https://api.proxyapi.ru/openai/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 60

    # --- Лимитирование ---
    rate_limit_per_minute: int = 5

    # --- Ограничения контракта ---
    max_text_length: int = 2000
    max_client_id_length: int = 128

    # --- Пути ---
    db_path: str = "data/tickets.db"
    log_dir: str = "logs"
    # База знаний для демо-режима (когда LLM_API_KEY не задан)
    knowledge_base_path: str = "examples/knowledge_base.json"

    # --- Запуск ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000


settings = Settings()
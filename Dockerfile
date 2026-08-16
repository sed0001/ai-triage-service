FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# База знаний для демо-режима без ключа LLM
COPY examples/knowledge_base.json ./examples/knowledge_base.json

# Директории для данных и логов создаются на старте, но создадим заранее
ENV DB_PATH=/app/data/tickets.db
ENV LOG_DIR=/app/logs
RUN mkdir -p /app/data /app/logs

EXPOSE 8000

# Ключ LLM передаётся при запуске контейнера, см. README
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
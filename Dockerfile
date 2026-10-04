FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Перед стартом применяем миграции БД (для PostgreSQL/Neon), затем запускаем бота
CMD ["sh", "-c", "alembic upgrade head && python main.py"]

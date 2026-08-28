FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 telegram-monitor
USER telegram-monitor
WORKDIR /home/telegram-monitor

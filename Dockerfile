FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Системные зависимости для Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libx11-xcb1 \
    libxext6 \
    libx11-6 \
    libxcb1 \
    libxrender1 \
    libfontconfig1 \
    libfreetype6 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Chromium с зависимостями через Playwright
RUN playwright install chromium --with-deps

COPY . .

CMD ["python", "-m", "winebot.bot"]

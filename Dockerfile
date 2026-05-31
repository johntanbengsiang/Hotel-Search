# Use slim Python base and install Chromium deps manually
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver libnss3 libnspr4 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 libx11-6 libx11-xcb1 \
    libxcb1 libxext6 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1001 appuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R appuser:appuser /app

USER appuser
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV PORT=10000
EXPOSE 10000

CMD gunicorn --bind 0.0.0.0:$PORT --timeout 120 --workers 1 app:app

RUN echo "=== DEBUG BUILD ==="
RUN pwd
RUN ls -la
RUN which chromium || true
RUN which chromium-browser || true
RUN chromium --version || true
RUN chromium-browser --version || true

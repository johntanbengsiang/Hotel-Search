# Python slim base — Playwright will install its own Chromium
FROM python:3.11-slim-bookworm

# System deps required by Playwright's Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's own Chromium + its missing OS deps
# This is the ONLY reliable way — do NOT set PLAYWRIGHT_BROWSERS_PATH or PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD
RUN playwright install chromium --with-deps

# Create non-root user AFTER playwright install (browsers are in /root/.cache, chown them)
RUN useradd -m -u 1000 appuser \
    && cp -r /root/.cache /home/appuser/.cache \
    && chown -R appuser:appuser /home/appuser/.cache

# Cache-bust: increment this number to force Docker to re-copy app files
ARG CACHE_BUST=2
# Copy app
COPY . .
RUN chown -R appuser:appuser /app

USER appuser

ENV PORT=10000
EXPOSE 10000

CMD gunicorn --bind 0.0.0.0:$PORT --timeout 120 --workers 1 app:app

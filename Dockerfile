# Playwright's official Python image — has Chromium + all system deps pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Create non-root user (required for Render + improves Chromium sandboxing)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install Python dependencies as root first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Fix ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user and install Playwright browsers for this user
USER appuser
RUN playwright install chromium

# Render assigns PORT via env var (default 10000)
ENV PORT=10000
EXPOSE 10000

# Use gunicorn for production (more stable than Flask dev server)
CMD gunicorn --bind 0.0.0.0:$PORT --timeout 120 --workers 1 app:app

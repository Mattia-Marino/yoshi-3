# Simple Dockerfile for a Python WSGI app (uses Gunicorn)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy app sources
COPY . .

# Ensure Gunicorn is available; install requirements if provided
RUN pip install --no-cache-dir gunicorn && \
    if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Configurable port and WSGI module (default expects `wsgi:app`)
ENV PORT=5000 WSGI_MODULE=wsgi:app

EXPOSE 5000

# Run the WSGI app via Gunicorn
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} ${WSGI_MODULE}"]

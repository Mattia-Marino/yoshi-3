# Dockerfile for Python gRPC Server
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app sources
COPY . .

# Expose the gRPC port defined in app.py
EXPOSE 50051

# Run the gRPC server
CMD ["python", "app.py"]

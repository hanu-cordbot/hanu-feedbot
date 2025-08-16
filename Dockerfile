# === ENHANCED DOCKERFILE FOR RAILWAY SERVERLESS ===

# Use Python slim image for better Railway compatibility
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port Railway expects
EXPOSE 8080

# Use Procfile command for Railway compatibility
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--timeout", "300", "--workers", "1"]

# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install build dependencies for TgCrypto and other C extensions
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (for better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its dependencies + browsers
RUN playwright install chromium
RUN apt-get update && playwright install-deps chromium && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code into the container
COPY . .

# Expose the port for health checks
EXPOSE 8080

# Command to run the application
CMD ["python", "bot.py"]

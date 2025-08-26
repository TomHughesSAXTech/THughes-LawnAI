FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY hughes_lawn_ai.py .
COPY grass.jpeg .

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Environment variables (will be overridden by Azure)
ENV ECOWITT_APP_KEY="14CF42F092D6CC8C5421160A37A0417A"
ENV ECOWITT_API_KEY="e5f2d6ff-2323-477e-8041-6e284b401b83"
ENV ECOWITT_MAC="34:94:54:96:22:F5"
ENV RAINBIRD_IP="q0852082.eero.online"
ENV N8N_WEBHOOK_URL="https://workflows.saxtechnology.com/webhook/hughes-lawn-ai"
ENV PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "app.py"]

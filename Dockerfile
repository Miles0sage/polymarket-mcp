FROM python:3.11-slim

LABEL maintainer="polymarket-agent"
LABEL description="Autonomous Polymarket prediction market trading agent"

# Prevent Python from buffering stdout/stderr (important for Docker logs)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default configuration
ENV PAPER_MODE=true
ENV SCAN_INTERVAL=900
ENV MAX_TRADE_SIZE=100
ENV DAILY_LOSS_LIMIT=500
ENV MAX_POSITIONS=10
ENV MIN_EDGE=0.05
ENV MIN_VOLUME=10000
ENV MIN_LIQUIDITY=5000
ENV BANKROLL=1000
ENV LOG_LEVEL=INFO

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Note: Use Railway Volumes for persistence (VOLUME keyword banned on Railway)
# https://docs.railway.com/reference/volumes

ENTRYPOINT ["python", "agent.py"]
CMD ["run"]

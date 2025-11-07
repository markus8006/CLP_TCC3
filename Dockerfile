FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpcap0.8 \
    libpcap0.8-dev \
    libffi-dev \
    libssl-dev \
    libsnap7-1 \
    libsnap7-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -ms /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

ENV FLASK_APP=run.py \
    FLASK_ENV=development \
    PYTHONPATH=/app

EXPOSE 5000

ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["python", "run.py"]

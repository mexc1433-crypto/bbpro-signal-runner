FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev libffi-dev curl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --no-deps numpy==1.24.0 \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=0
ENV MALLOC_TRIM_THRESHOLD_=65536

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-O", "bot/main.py"]

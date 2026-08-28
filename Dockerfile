# Changed base tag to force full rebuild
FROM python:3.11.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev libffi-dev curl

WORKDIR /app

# Install ALL deps directly
RUN pip install --no-cache-dir \
    python-telegram-bot==20.7 \
    yfinance==0.2.40 \
    "pandas==2.2.0" \
    "numpy==1.26.4" \
    ta==0.11.0 \
    python-dotenv==1.0.1 \
    schedule==1.2.1 \
    "requests==2.31.0" \
    aiohttp==3.9.3 \
    ccxt==4.5.75 \
    "cryptography>=42.0.0"

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=0

CMD ["python", "-O", "main.py"]

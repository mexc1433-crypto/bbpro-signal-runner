FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libssl-dev libffi-dev curl

WORKDIR /app

COPY requirements.txt .
# Force fresh pip install (no Docker layer cache)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=0

CMD ["python", "-O", "main.py"]

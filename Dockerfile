FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системні пакети не потрібні: усі залежності ставляться з готових wheel-ів
COPY requirements.txt /app/
RUN pip install -r requirements.txt

RUN mkdir -p /app/audio

COPY . /app/

CMD ["python", "main.py"]

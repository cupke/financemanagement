# Образ backend FinTrack для разработки.
# В production будет multi-stage сборка с минимальным runtime-образом без dev-зависимостей;
# на этом этапе достаточно одного простого образа.
FROM python:3.13-slim

# /app — рабочая папка внутри контейнера. Сюда docker-compose смонтирует код с хоста.
WORKDIR /app

# Системные пакеты:
#   libpq5         — runtime-библиотека для psycopg (динамическая линковка с PostgreSQL)
#   curl           — пригодится для healthcheck в будущем
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Сначала ставим зависимости — они меняются реже самого кода, поэтому Docker
# переиспользует этот слой при пересборке кода.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# В dev-режиме код проекта монтируется volume-ом из docker-compose.yml в /app,
# поэтому COPY . . здесь не делаем (иначе при первом старте код взялся бы из
# образа, а потом закрылся volume-ом — это создаёт путаницу).

EXPOSE 8000

# uvicorn в reload-режиме автоматически перезапускается при изменениях файлов
# в /app (которые проходят через volume-mount с хоста).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

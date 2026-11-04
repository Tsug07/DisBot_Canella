# Imagem unica dos bots Discord na VPS. Cada bot e um servico do
# docker-compose.yml que roda o seu script a partir desta mesma imagem.
#
# 3.12 e nao 3.13: o discord.py 2.3.2 importa `audioop`, removido no 3.13.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo \
    BOT_SEM_LOCK=1

RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-docker.txt .
RUN pip install -r requirements-docker.txt

# Codigo apenas. Segredos (.env) e estado ficam de fora pelo .dockerignore e
# chegam pelo docker-compose (env_file e a pasta _vps/).
COPY Bot_Bip/ Bot_Bip/
COPY Bot_Rebecca/ Bot_Rebecca/
COPY Bot_Gerson/ Bot_Gerson/
COPY controle/ controle/

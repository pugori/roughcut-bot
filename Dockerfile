FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir discord.py modal requests

COPY . .

ENV PYTHONUNBUFFERED=1
ENV USE_MODAL_CLOUD=1
ENV PORT=10000
ENV MODAL_TOKEN_ID="ak-FkEQy9BJkBw1461Ilh0MyN"
ENV MODAL_TOKEN_SECRET="as-aEuTPFrqSBlMLQtkeZakXf"

EXPOSE 10000

CMD ["python", "-m", "bot.discord_bot"]

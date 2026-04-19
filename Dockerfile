# Number store Telegram bot — single-stage image (no requirements.txt).
# Set secrets at runtime, e.g. -e MONGODB_URI=... (see bot.py for env names).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ca-certificates: TLS to MongoDB Atlas / GitHub / Telegram API
# git: optional; needed only if you mount a git checkout and use /update with git pull
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# Python deps (pinned loosely for reproducible builds; bump as needed)
RUN pip install \
    "python-telegram-bot>=21.0,<23" \
    "telethon>=1.34,<2" \
    "pymongo[srv]>=4.6,<5" \
    "qrcode[pil]>=7.4,<9"

COPY bot.py i18n.py en.json ./

# Non-root process (adjust UID if your platform requires a specific user)
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-u", "bot.py"]

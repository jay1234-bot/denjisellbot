# Number store Telegram bot — single-stage image (no requirements.txt).
# Required: -e MONGODB_URI=...
# Optional Mongo (see bot.py): MONGODB_TLS_CA_FILE, MONGODB_TLS_STRICT=1, MONGODB_TLS_NO_WORKAROUND=1,
#   MONGODB_TLS_INSECURE=1, MONGODB_ALLOW_IPV6=1, MONGODB_NO_TLS_FALLBACK=1 (disables insecure retry).

# Python 3.11 avoids several Atlas TLS handshake issues seen with 3.12 + OpenSSL 3.2
# (e.g. SSL: TLSV1_ALERT_INTERNAL_ERROR on mongodb+srv from slim containers).
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Kolkata \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# openssl: full TLS stack for PyMongo; ca-certificates: trust store for Atlas / APIs
# git: optional; for /update when the app directory is a git checkout
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl git tini tzdata \
    && rm -rf /var/lib/apt/lists/*

# certifi: explicit CA bundle passed to MongoClient (see get_mongo_client in bot.py)
RUN pip install \
    "python-telegram-bot>=21.0,<23" \
    "telethon>=1.34,<2" \
    "pymongo[srv]>=4.8,<5" \
    "qrcode[pil]>=7.4,<9" \
    "certifi>=2024.0.0" \
    "dnspython>=2.6,<3"

COPY bot.py i18n.py en.json ./

# Non-root process (adjust UID if your platform requires a specific user)
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-u", "bot.py"]

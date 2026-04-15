FROM python:3.11-slim

WORKDIR /app

# Install dependencies directly — no requirements.txt needed
RUN pip install --no-cache-dir \
    "python-telegram-bot>=20.0" \
    "telethon>=1.34" \
    "qrcode>=7.4" \
    "Pillow>=9.0" \
    "aiohttp"

# Copy bot file
COPY bot.py .

CMD ["python", "bot.py"]

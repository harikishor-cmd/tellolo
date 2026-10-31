# Tellolo on Render (or any Docker host). ffmpeg comes from Debian's package, not Render's native runtime.
FROM python:3.13.5-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 tellolo && mkdir -p data && chown tellolo data
USER tellolo
ENV PYTHONUNBUFFERED=1
# Render sets PORT; app.py then binds 0.0.0.0:$PORT.
CMD ["python3", "app.py"]

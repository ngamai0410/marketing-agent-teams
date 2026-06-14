# Build context = embroidery/  (the package root: holds config.yaml, fixtures/, tests/).
#   docker build -t embroidery-dashboard .
FROM python:3.11-slim

# Keep Python lean + unbuffered so logs stream to docker/Caddy in real time.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EMBROIDERY_WEB_HOST=0.0.0.0 \
    EMBROIDERY_WEB_PORT=8765

WORKDIR /app

# Deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + committed config/fixtures. data/ is a mounted volume (see compose),
# NOT baked into the image — artifacts must survive restarts.
COPY embroidery ./embroidery
COPY config.yaml ./config.yaml
COPY fixtures ./fixtures

EXPOSE 8765

# --no-browser: headless container must not try to open a local browser.
CMD ["python", "-m", "embroidery.web", "--no-browser"]

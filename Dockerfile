FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    YDL_SESSION_ROOT=/tmp/ydl-sessions \
    YDL_TEMPLATE_PATH=/data/digit_templates_user.npz

RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      fonts-dejavu-core \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY analyzer_core.py app.py digit_templates.npz ./
COPY static ./static

# OpenShift/Rahti assigns an arbitrary UID that is a member of group 0.
RUN mkdir -p /data /tmp/ydl-sessions \
    && chgrp -R 0 /app /data /tmp/ydl-sessions \
    && chmod -R g=u /app /data /tmp/ydl-sessions

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]

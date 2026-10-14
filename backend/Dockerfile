FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Moscow DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gigo ./gigo
RUN useradd --system --uid 10001 gigo && mkdir -p /app/data && chown gigo /app/data
USER gigo
CMD ["uvicorn", "gigo.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

FROM python:3.11-slim

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

RUN groupadd -g 10001 appgroup && useradd -u 10001 -g appgroup -M appuser \
    && mkdir -p uploads secure_uploads public_assets temp_pdfs \
    && chown -R appuser:appgroup /app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

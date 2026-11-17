FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
# opentelemetry-bootstrap installs the instrumentations for the libraries found
# (FastAPI, SQLAlchemy, psycopg, logging), so spans and logs are produced automatically.
RUN pip install --no-cache-dir -r requirements.txt \
    && opentelemetry-bootstrap -a install

COPY app.py .

EXPOSE 8080
# One worker: the pool lives in this process, so the fault endpoint affects all requests.
CMD ["opentelemetry-instrument", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

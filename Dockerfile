FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Backend/ ./Backend/

WORKDIR /app/Backend

EXPOSE 8000

CMD ["uvicorn", "join_app:app", "--host", "0.0.0.0", "--port", "8000"]

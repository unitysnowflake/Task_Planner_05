FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["uvicorn", "goal_service:app", "--host", "0.0.0.0", "--port", "8002"]

FROM python:3.11-slim

WORKDIR /app

COPY main.py .
COPY landing.html .

EXPOSE 8080

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD ["python3", "main.py"]

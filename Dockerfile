FROM python:3.11-slim

WORKDIR /app

# Copy only requirements and app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY . .

# Expose the configured port
EXPOSE 8080

# Container healthcheck: validates the running app is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python /app/tests/smoke_check.py || exit 1

# Run the server
CMD ["python", "server.py"]

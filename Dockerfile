FROM python:3.11-slim

WORKDIR /app

# Copy only requirements and server
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application
COPY . .

# Expose the configured port
EXPOSE 8080

# Run the server
CMD ["python", "server.py"]

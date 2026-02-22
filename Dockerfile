# Use the official Playwright Python image (Ubuntu Jammy based)
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Set the working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# We don't need to run `playwright install` because the base image already has the browsers!

# Copy your API code
COPY api.py .

# Expose the API port
EXPOSE 8000

# Start the FastAPI server
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
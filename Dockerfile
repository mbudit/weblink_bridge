# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY requirements.txt .
COPY bridge.py .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run bridge.py with waitress (production WSGI server)
CMD ["python", "-c", "from bridge import app, init_db; init_db(); import waitress; waitress.serve('bridge:app', host='0.0.0.0', port=5000)"]
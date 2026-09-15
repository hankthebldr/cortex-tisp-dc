# Dockerfile - REPLACE THIS WITH YOUR APPLICATION'S DOCKERFILE
#
# This is a placeholder. You must create a Dockerfile for your specific language/framework.
# See Dockerfile.example for examples of Node.js, Python, Go, etc.
#
# REQUIREMENTS:
# 1. Your app MUST listen on port 8080 (standardized across all languages)
# 2. EXPOSE 8080 in your Dockerfile
# 3. Implement a /health endpoint that returns HTTP 200
# 4. Run as non-root user for security
# 5. Keep image size small (use multi-stage builds)
# 6. Use docker-io.art.code.pan.run for Docker Hub images (avoids rate limits)
#
# IMPORTANT: Always use docker-io.art.code.pan.run instead of docker.io
# This is Palo Alto Networks' internal Artifactory proxy for Docker Hub.
#
# Example for Python:
#   FROM docker-io.art.code.pan.run/library/python:3.11-slim
#   WORKDIR /app
#   COPY requirements.txt .
#   RUN pip install -r requirements.txt
#   COPY . .
#   EXPOSE 8080
#   CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]

# YOUR DOCKERFILE GOES HERE
# Delete these comments and the error code below, then add your build instructions

# ==========================================
# DELETE EVERYTHING BELOW THIS LINE
# This code is only here to fail the build if you forget to customize the Dockerfile
# ==========================================
FROM docker-io.art.code.pan.run/library/alpine:latest
RUN echo "ERROR: You must customize the Dockerfile for your application!" && exit 1

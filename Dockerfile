# Use the official lightweight Python image.
FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the logs
ENV PYTHONUNBUFFERED=True

# Copy local code to the container image.
ENV APP_HOME=/app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port Streamlit runs on
EXPOSE 8080

# Run the web service on container startup.
# Cloud Run expects the app to listen on PORT 8080 (Streamlit default is 8501)
CMD streamlit run app.py --server.port=8080 --server.address=0.0.0.0
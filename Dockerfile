# Use 3.13 to match your local environment (TaskGroups, etc.)
FROM python:3.13-slim

# Allow statements and log messages to immediately appear in the logs
ENV PYTHONUNBUFFERED=True

# System dependencies (Required for ReportLab & Jina)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy local code to the container image
ENV APP_HOME=/app
WORKDIR $APP_HOME

# Copy and install dependencies first (caching optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . ./

# Make the batch script executable
COPY run.sh .
RUN chmod +x run.sh

# Expose the port Streamlit runs on
EXPOSE 8080

# --- DEFAULT COMMAND (The Web App) ---
# This ensures that standard Cloud Run deployments launch Streamlit.
CMD streamlit run app.py --server.port=8080 --server.address=0.0.0.0

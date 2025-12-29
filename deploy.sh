#!/bin/bash

# 1. Load variables from .env file
# (This trick exports all your .env vars into the current shell session)
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
else
  echo "❌ .env file not found!"
  exit 1
fi

echo "🚀 Deploying Marketing Analyst App..."

# 2. Deploy Web App (Service) with all secrets
gcloud run deploy marketing-analyst-app \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --update-env-vars PROJECT_ID="$PROJECT_ID" \
  --update-env-vars ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  --update-env-vars GMAIL_USER="$GMAIL_USER" \
  --update-env-vars GMAIL_APP_PASSWORD="$GMAIL_APP_PASSWORD" \
  --update-env-vars GOOGLE_API_KEY="$GOOGLE_API_KEY" \
  --update-env-vars SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN" \
  --update-env-vars SLACK_CHANNEL_ID="$SLACK_CHANNEL_ID"

echo "✅ Web App Deployed!"

# 3. Update the Job (Daily Runner) with the same image and secrets
# Note: Jobs use the container image, so we rebuild that first if needed.
# ideally, we build the image once and use it for both, but for now let's just update the config.

echo "⚙️ Updating Daily Job Configuration..."
gcloud run jobs update daily-brief-job \
  --image gcr.io/marketing-analyst-prod/hybrid-agent \
  --update-env-vars PROJECT_ID="$PROJECT_ID" \
  --update-env-vars GMAIL_USER="$GMAIL_USER" \
  --update-env-vars GMAIL_APP_PASSWORD="$GMAIL_APP_PASSWORD" \
  --update-env-vars GOOGLE_API_KEY="$GOOGLE_API_KEY" \
  --update-env-vars SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN" \
  --update-env-vars SLACK_CHANNEL_ID="$SLACK_CHANNEL_ID"

echo "✅ Job Updated!"
import os
import asyncio
import agent
import utils
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from google.cloud import firestore


# --- SLACK HELPER ---
def post_to_slack(summary_text, pdf_bytes=None, filename=None):
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        print("❌ Slack config missing.")
        return

    client = WebClient(token=token)
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 Daily Intel: {datetime.now().strftime('%Y-%m-%d')}",
            },
        },
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary_text}},
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "Detailed analysis is attached below."}
            ],
        },
    ]

    try:
        client.chat_postMessage(channel=channel, blocks=blocks, text="Daily Update")
        if pdf_bytes:
            client.files_upload_v2(
                channel=channel, content=pdf_bytes, filename=filename
            )
        print("✅ Slack notified.")
    except SlackApiError as e:
        print(f"❌ Slack Error: {e.response['error']}")


# --- MAIN LOGIC ---
async def run_daily_brief():
    print(f"🚀 Starting Daily Brief: {datetime.now()}")

    # 1. SETUP DATA FROM FIRESTORE
    db = firestore.Client()

    # Get Competitors from Firestore (Corrected Query)
    # We simplified the collection, so we just stream all docs
    comp_docs = db.collection("competitors").stream()
    competitors = [doc.id for doc in comp_docs]

    # Load Memory for Diffing
    memory = utils.load_memory()

    # Fallback if Firestore is empty
    if not competitors:
        print("⚠️ No competitors in Firestore. Using defaults.")
        competitors = ["navistone.com", "pebblepost.com"]

    full_report_data = []
    slack_summary_lines = []

    # 2. ANALYSIS LOOP
    for domain in competitors:
        print(f"--- Analyzing {domain} ---")

        # Get previous analysis from memory (if any)
        prev_analysis = memory.get(domain, "No previous data.")

        try:
            # Call Agent with context about the previous state
            prompt = f"Analyze {domain}. PREVIOUS ANALYSIS: {prev_analysis}"

            analysis_result = await agent.run_agent_turn(
                prompt, chat_history=[], headless=True
            )

            # Store structured data for the PDF
            full_report_data.append(
                {
                    "name": analysis_result.name,
                    "content": {
                        "value_proposition": analysis_result.value_proposition,
                        "solutions": analysis_result.solutions,
                        "industries": analysis_result.industries,
                    },
                    "has_changes": analysis_result.has_changes,
                }
            )

            # Update memory with the latest text representation for next time
            memory[domain] = (
                f"Value Prop: {analysis_result.value_proposition} | "
                f"Solutions: {analysis_result.solutions} | "
                f"Industries: {analysis_result.industries}"
            )

            # Build Slack Status
            icon = "🟢" if analysis_result.has_changes else "⚪"
            slack_summary_lines.append(
                f"{icon} *{analysis_result.name}*: Analysis Complete"
            )

        except Exception as e:
            print(f"❌ Error analyzing {domain}: {e}")
            slack_summary_lines.append(f"⚠️ *{domain}*: Error ({str(e)})")

    # Save updated memory back to cloud
    utils.save_memory(memory)

    # 3. GENERATE PDF (Passing the LIST, not a string)
    # Ensure your utils.create_pdf is updated to handle this list!
    pdf_bytes = utils.create_pdf(full_report_data)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"Daily_Brief_{date_str}.pdf"

    # 4. SEND EMAILS TO ACTIVE SUBSCRIBERS
    subscribers = db.collection("subscribers").where("status", "==", "active").stream()
    subscriber_emails = [doc.to_dict()["email"] for doc in subscribers]

    if subscriber_emails:
        for email in subscriber_emails:
            print(f"📧 Sending to {email}...")
            utils.send_email(
                subject=f"Daily Competitive Brief - {date_str}",
                recipient_email=email,
                body_text="Attached is your daily competitive intelligence strategy report.",
                pdf_bytes=pdf_bytes,
                filename=filename,
            )
    else:
        print("⚠️ No subscribers found. Sending to default admin.")
        utils.send_email(
            subject="Internal Test Report",
            recipient_email="jaybeaux@gmail.com",
            body_text="No active subscribers found. Here is the test report.",
            pdf_bytes=pdf_bytes,
            filename=filename,
        )

    # 5. SEND TO SLACK
    final_summary = "\n".join(slack_summary_lines)
    post_to_slack(final_summary, pdf_bytes, filename)


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

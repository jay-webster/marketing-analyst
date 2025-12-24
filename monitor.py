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

    db = firestore.Client(project="marketing-analyst-prod")

    # 1. BROAD FETCH COMPETITORS (Ensures we don't skip anyone)
    comp_docs = db.collection("competitors").stream()
    competitors = [doc.id for doc in comp_docs]

    # 2. LOAD MEMORY (The Baseline)
    memory = utils.load_memory()
    print(f"DEBUG: Loaded memory for {len(memory)} domains.")

    if not competitors:
        print("⚠️ No competitors in Firestore. Using defaults.")
        competitors = ["navistone.com", "pebblepost.com"]

    full_report_data = []
    slack_summary_lines = []

    # 3. ANALYSIS LOOP
    for domain in competitors:
        print(f"--- Analyzing {domain} ---")

        # Check if this is the first time we see this domain
        prev_analysis = memory.get(domain)
        is_baseline = prev_analysis is None

        try:
            print(f"DEBUG: Calling agent for {domain}...")
            analysis_result = await agent.run_agent_turn(
                f"Analyze {domain}", [], headless=True
            )

            # Check if the agent returned the failure object
            if "Error" in analysis_result.name or "Failed" in analysis_result.name:
                print(
                    f"⚠️ Agent returned a failure object for {domain}: {analysis_result.value_proposition}"
                )

            full_report_data.append(
                {
                    "name": (
                        domain
                        if "Error" in analysis_result.name
                        else analysis_result.name
                    ),
                    "content": {
                        "value_proposition": analysis_result.value_proposition,
                        "solutions": analysis_result.solutions,
                        "industries": analysis_result.industries,
                    },
                    "has_changes": True,
                }
            )
            memory[domain] = analysis_result.value_proposition
            slack_summary_lines.append(f"🟢 *{domain}*: Analysis Complete")

        except Exception as e:
            # THIS IS THE CRITICAL LOG LINE
            print(f"❌ CRITICAL ERROR on {domain}: {type(e).__name__} - {str(e)}")
            slack_summary_lines.append(f"⚠️ *{domain}*: Analysis Failed")

    # 5. SAVE MEMORY BACK TO GCS
    utils.save_memory(memory)

    # 6. GENERATE PDF
    pdf_bytes = utils.create_pdf(full_report_data)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"Daily_Brief_{date_str}.pdf"

    # 7. SEND EMAILS
    subscribers = db.collection("subscribers").where("status", "==", "active").stream()
    subscriber_emails = [doc.to_dict()["email"] for doc in subscribers]

    if not subscriber_emails:
        subscriber_emails = ["jaybeaux@gmail.com"]  # Default fallback

    for email in subscriber_emails:
        utils.send_email(
            subject=f"Daily Competitive Brief - {date_str}",
            recipient_email=email,
            body_text="Attached is your daily competitive intelligence strategy report.",
            pdf_bytes=pdf_bytes,
            filename=filename,
        )

    # 8. SEND TO SLACK
    post_to_slack("\n".join(slack_summary_lines), pdf_bytes, filename)


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

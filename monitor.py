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
# --- MAIN LOGIC ---
async def run_daily_brief():
    print(f"🚀 Starting Daily Brief: {datetime.now()}")

    db = firestore.Client(project="marketing-analyst-prod")

    # 1. FETCH COMPETITORS
    comp_docs = db.collection("competitors").stream()
    competitors = [doc.id for doc in comp_docs]

    # 2. LOAD MEMORY
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
        prev_analysis = memory.get(domain)  # Capture the previous state for comparison

        try:
            print(f"DEBUG: Calling agent for {domain}...")
            # Headless run to get structured data
            analysis_result = await agent.run_agent_turn(
                f"Analyze {domain}", [], headless=True
            )

            # Determine name for the report
            report_name = (
                domain if "Error" in analysis_result.name else analysis_result.name
            )

            full_report_data.append(
                {
                    "name": report_name,
                    "content": {
                        "value_proposition": analysis_result.value_proposition,
                        "solutions": analysis_result.solutions,
                        "industries": analysis_result.industries,
                    },
                    "old_content": prev_analysis,  # Store old content for the PDF's Comparison View
                    "has_changes": (
                        True
                        if prev_analysis != analysis_result.value_proposition
                        else False
                    ),
                }
            )

            # Update memory only if successful
            if "Error" not in analysis_result.name:
                memory[domain] = analysis_result.value_proposition

            slack_summary_lines.append(f"🟢 *{domain}*: Analysis Complete")

        except Exception as e:
            print(f"❌ CRITICAL ERROR on {domain}: {str(e)}")
            slack_summary_lines.append(f"⚠️ *{domain}*: Analysis Failed")

    # 4. FINAL SYNTHESIS: THE ANALYST SUMMARY
    # Collect all findings to give the agent a "holistic" view of the market
    all_findings = "\n".join(
        [f"{c['name']}: {c['content']['value_proposition']}" for c in full_report_data]
    )

    summary_prompt = f"Act as a CMO. Write a 3-sentence executive summary of the following market updates: {all_findings}"
    print("🧠 Generating Executive Analyst Summary...")
    analyst_summary = await agent.run_agent_turn(summary_prompt, [], headless=False)

    # 5. SAVE MEMORY & GENERATE PDF
    utils.save_memory(memory)

    # Pass the analyst_summary into your new create_pdf function
    pdf_bytes = utils.create_pdf(full_report_data, analyst_summary)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"Daily_Brief_{date_str}.pdf"

    # 6. SEND NOTIFICATIONS
    # # --- 6. SEND EMAILS ---
    subscribers = db.collection("subscribers").where("status", "==", "active").stream()
    subscriber_emails = [doc.to_dict()["email"] for doc in subscribers]

    # Fallback if no subscribers found
    if not subscriber_emails:
        subscriber_emails = ["jaybeaux@gmail.com"]

    for email in subscriber_emails:
        print(f"📧 Sending brief to {email}...")
        utils.send_email(
            subject=f"Daily Competitive Brief - {date_str}",
            recipient_email=email,
            body_text=f"Attached is your daily report.\n\nAnalyst Summary: {analyst_summary}",
            pdf_bytes=pdf_bytes,
            filename=filename,
        )

    # Update Slack to include the high-level analyst summary
    post_to_slack(
        f"*Analyst Summary:*\n{analyst_summary}\n\n" + "\n".join(slack_summary_lines),
        pdf_bytes,
        filename,
    )


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

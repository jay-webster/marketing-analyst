import os
import asyncio
import agent
import utils
import json
from types import SimpleNamespace
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from google.cloud import firestore

# FIX 1: Import FieldFilter for modern queries
from google.cloud.firestore import FieldFilter
from linkedin_tracker import LinkedInTracker

# --- CONFIGURATION ---
REFERENCE_DOMAIN = "navistone.com"
REFERENCE_NAME = "NaviStone"


# --- SLACK HELPER ---
def post_to_slack(summary_text, pdf_bytes=None, filename=None):
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        print("❌ Slack config missing.")
        return

    client = WebClient(token=token)

    # If no PDF (Simple update mode)
    if not pdf_bytes:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📊 *Daily Intel ({datetime.now().strftime('%Y-%m-%d')})*",
                },
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": summary_text}},
        ]
        text_msg = "Daily Update: No Changes"
    else:
        # Full Report Mode
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
        text_msg = "Daily Update"

    try:
        client.chat_postMessage(channel=channel, blocks=blocks, text=text_msg)
        if pdf_bytes:
            client.files_upload_v2(
                channel=channel, content=pdf_bytes, filename=filename
            )
        print("✅ Slack notified.")
    except SlackApiError as e:
        print(f"❌ Slack Error: {e.response['error']}")


# --- LINKEDIN HELPER ---
async def check_linkedin_updates(company_name, domain):
    print(f"\n--- 🕵️‍♂️ Starting LinkedIn Check for {company_name} ---")
    tracker = LinkedInTracker(agent_module=agent, use_mock=False)
    try:
        result = await tracker.get_company_updates(company_name, domain)
        print(f"✅ STATUS: Success")
        return result
    except Exception as e:
        print(f"❌ STATUS: Failed ({e})")
        return None


# --- MAIN LOGIC ---
async def run_daily_brief():
    print(f"🚀 Starting Daily Brief: {datetime.now()}")
    db = firestore.Client(project="marketing-analyst-prod")

    # 1. Fetch Competitors
    comp_docs = db.collection("competitors").stream()
    competitors = [doc.id for doc in comp_docs]
    memory = utils.load_memory()

    if not competitors:
        print("⚠️ No competitors. Using defaults.")
        competitors = ["pebblepost.com", "lob.com", "postie.com", "postpilot.com"]

    # EXCLUDE REFERENCE COMPANY
    if REFERENCE_DOMAIN in competitors:
        competitors.remove(REFERENCE_DOMAIN)

    updates_found = []

    # 3. Analysis Loop
    for domain in competitors:
        print(f"--- Analyzing {domain} ---")
        company_name = domain.split(".")[0].capitalize()
        prev_analysis = memory.get(domain)
        website_result = None
        linkedin_result = None
        website_changed = False

        # A. Website Analysis
        try:
            print(f"DEBUG: Calling agent for website analysis on {domain}...")
            analysis_prompt = (
                f"Analyze the website {domain} using the scrape_website tool. "
                f"Return a valid JSON object (NO markdown) with these keys: "
                f"name, value_proposition, solutions, industries. "
                f"If site is inaccessible, return JSON with 'value_proposition': 'Could not access website.'."
            )

            raw_response = await agent.run_agent_turn(
                analysis_prompt, [], headless=True
            )

            # Clean Response
            clean_json = raw_response.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            if clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]

            if not clean_json:
                raise ValueError("Empty response")

            data_dict = json.loads(clean_json)
            website_result = SimpleNamespace(**data_dict)

        except Exception as e:
            print(f"❌ Website Analysis Failed: {e}")
            website_result = SimpleNamespace(
                name=domain,
                value_proposition="Analysis failed.",
                solutions="N/A",
                industries="N/A",
            )

        # B. LinkedIn Analysis
        try:
            linkedin_result = await check_linkedin_updates(company_name, domain)
        except Exception as e:
            print(f"❌ LinkedIn Analysis Failed: {e}")

        # C. Check for Changes
        current_val_prop = getattr(website_result, "value_proposition", "N/A")

        # Check 1: Website Value Prop Changed?
        # Only mark as changed if it's NOT a failure message
        if (prev_analysis != current_val_prop) and (
            "Analysis failed" not in current_val_prop
        ):
            website_changed = True

        # Check 2: LinkedIn News Exists?
        li_summary = "No recent updates found."
        news_found = False
        if linkedin_result and linkedin_result.summary_text:
            li_summary = linkedin_result.summary_text
            if len(li_summary) > 50 and "No recent updates" not in li_summary:
                news_found = True

        # FILTER LOGIC
        if website_changed or news_found:

            updates_found.append(
                {
                    "name": getattr(website_result, "name", domain),
                    "content": {
                        "value_proposition": current_val_prop,
                        "solutions": getattr(website_result, "solutions", "N/A"),
                        "industries": getattr(website_result, "industries", "N/A"),
                    },
                    "linkedin_update": li_summary,
                    "old_content": prev_analysis,
                    "has_changes": website_changed,
                }
            )

            # Update memory
            memory[domain] = current_val_prop
            print(f"✅ Update found for {domain}")
        else:
            print(f"💤 No significant updates for {domain}")

        print("⏳ Pausing briefly...")
        await asyncio.sleep(5)

    # 4. DECISION: GENERATE REPORT OR NOT?
    if not updates_found:
        print("📉 No updates found for any competitor. Sending simple notification.")
        msg = "No significant updates in the competitive environment today."
        post_to_slack(msg)
        return

    # 5. Final Synthesis
    print(f"📝 Generating Summary for {len(updates_found)} active competitors...")

    all_findings = []
    for c in updates_found:
        summary_text = f"{c['name']}: {c['content']['value_proposition']}"
        if c.get("linkedin_update"):
            summary_text += f"\n   - Recent News: {c['linkedin_update'][:200]}..."
        all_findings.append(summary_text)

    summary_prompt = (
        f"Act as a CMO. Write a 3-sentence executive summary of these market updates. "
        f"Do NOT use introductory phrases like 'Here is a summary'. "
        f"Start directly with the insights.\n\nUpdates:\n{all_findings}"
    )

    analyst_summary = await agent.run_agent_turn(summary_prompt, [], headless=False)

    # 6. Save & Notify
    utils.save_memory(memory)

    pdf_bytes = utils.create_pdf(
        updates_found, analyst_summary, reference_company=REFERENCE_NAME
    )

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"Daily_Brief_{date_str}.pdf"

    # FIX 2: Use FieldFilter for modern Firestore query syntax
    subscribers = (
        db.collection("subscribers")
        .where(filter=FieldFilter("status", "==", "active"))
        .stream()
    )
    subscriber_emails = [doc.to_dict()["email"] for doc in subscribers]

    if not subscriber_emails:
        subscriber_emails = ["jaybeaux@gmail.com"]

    for email in subscriber_emails:
        print(f"📧 Sending brief to {email}...")
        utils.send_email(
            subject=f"Daily Competitive Brief - {date_str}",
            recipient_email=email,
            body_text=f"Attached is the daily report for {REFERENCE_NAME}.\n\nAnalyst Summary:\n{analyst_summary}",
            pdf_bytes=pdf_bytes,
            filename=filename,
        )

    post_to_slack(f"*Analyst Summary:*\n{analyst_summary}", pdf_bytes, filename)


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

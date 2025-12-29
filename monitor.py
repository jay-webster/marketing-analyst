import os
import asyncio
import agent
import utils
import json
import re
from types import SimpleNamespace
from datetime import datetime
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from google.cloud import firestore
from google.cloud.firestore import FieldFilter
from linkedin_tracker import LinkedInTracker

load_dotenv()
REFERENCE_DOMAIN = "navistone.com"
REFERENCE_NAME = "NaviStone"


# --- HELPER: POST TO SLACK ---
def post_to_slack(summary_text, pdf_bytes=None, filename=None):
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        return

    client = WebClient(token=token)

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
    except SlackApiError as e:
        print(f"❌ Slack Error: {e.response['error']}")


# --- HELPER: NEW DISCOVERY FUNCTION ---
async def discover_competitors(target_domain):
    """
    Uses the Agent to find top 5 competitors for a given domain.
    Returns a list of dicts: [{'name':..., 'domain':..., 'reason':...}]
    """
    print(f"🔭 Starting competitor discovery for {target_domain}...")

    prompt = (
        f"I need to identify the top 5 direct competitors for {target_domain}. "
        f"Use Google Search to find companies that offer similar products/services and target the same audience.\n"
        f"For each competitor, provide:\n"
        f"1. Name\n"
        f"2. Domain (e.g., competitor.com)\n"
        f"3. Reason (1 short sentence explaining why they are a competitor).\n\n"
        f"Return a VALID JSON object with a key 'competitors' containing a list of objects with keys: 'name', 'domain', 'reason'."
    )

    try:
        # Run agent (headless=True is fine here)
        raw_response = await agent.run_agent_turn(prompt, [], headless=True)
        print(f"🔎 Agent Discovery Output: {raw_response[:100]}...")

        # Robust JSON Parsing
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return data.get("competitors", [])
        else:
            print("❌ No JSON found in discovery response.")
            return []

    except Exception as e:
        print(f"❌ Discovery failed: {e}")
        return []


# --- EXISTING: LINKEDIN CHECKER ---
async def check_linkedin_updates(company_name, domain):
    print(f"\n--- 🕵️‍♂️ Starting LinkedIn Check for {company_name} ---")
    tracker = LinkedInTracker(agent_module=agent, use_mock=False)
    try:
        return await tracker.get_company_updates(company_name, domain)
    except Exception:
        return None


# --- EXISTING: WEBSITE ANALYSIS ---
async def analyze_competitor_website(domain):
    urls_to_try = [f"https://{domain}", f"https://www.{domain}"]

    # 1. Try Direct Scraping
    for url in urls_to_try:
        print(f"🕵️‍♂️ Attempting scrape of: {url}")
        try:
            analysis_prompt = (
                f"Analyze the website {url} using the scrape_website tool. "
                f"If the scrape returns empty or 'blocked', use your internal knowledge to describe {domain}. "
                f"Return a JSON object with these EXACT keys: 'name', 'value_proposition', 'solutions', 'industries'. "
                f"Do NOT return 'N/A' or 'Blocked'. Fill the fields with your best analysis of the company."
            )
            raw_response = await agent.run_agent_turn(
                analysis_prompt, [], headless=True
            )

            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                if data.get("value_proposition") not in [
                    "N/A",
                    "BLOCKED",
                    None,
                    "Could not access website.",
                ]:
                    return SimpleNamespace(**data)
        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")

    # 2. Fallback: Pure Inference
    print(f"⚠️ Scraping failed. Switching to analytical inference for {domain}.")
    try:
        fallback_prompt = (
            f"You are a CMO. I need a strategic profile of the company '{domain}'. "
            f"I cannot access their website right now, so use your internal training data to generate this profile. "
            f"Return valid JSON with keys: 'name', 'value_proposition', 'solutions', 'industries'."
        )
        raw_response = await agent.run_agent_turn(fallback_prompt, [], headless=True)
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if json_match:
            return SimpleNamespace(**json.loads(json_match.group(0)))
    except Exception:
        pass

    return SimpleNamespace(
        name=domain,
        value_proposition="Analysis currently unavailable.",
        solutions="N/A",
        industries="N/A",
    )


# --- MAIN JOB ---
async def run_daily_brief():
    print(f"🚀 Starting Daily Brief: {datetime.now()}")
    db = firestore.Client(project=os.getenv("PROJECT_ID", "marketing-analyst-prod"))

    comp_docs = db.collection("competitors").stream()
    competitors = [doc.id for doc in comp_docs]
    memory = utils.load_memory()

    if not competitors:
        competitors = ["pebblepost.com", "lob.com"]
    if REFERENCE_DOMAIN in competitors:
        competitors.remove(REFERENCE_DOMAIN)

    updates_found = []

    for domain in competitors:
        print(f"--- Analyzing {domain} ---")
        company_name = domain.split(".")[0].capitalize()

        website_result = await analyze_competitor_website(domain)
        linkedin_result = await check_linkedin_updates(company_name, domain)

        prev_data = memory.get(domain, {})
        if isinstance(prev_data, str):
            prev_val_prop = prev_data
        else:
            prev_val_prop = prev_data.get("content", {}).get("value_proposition")

        current_val_prop = getattr(website_result, "value_proposition", "N/A")

        website_changed = False
        if (
            (prev_val_prop != current_val_prop)
            and ("Analysis currently unavailable" not in current_val_prop)
            and ("N/A" not in current_val_prop)
        ):
            website_changed = True

        li_summary = (
            linkedin_result.summary_text
            if (linkedin_result and len(linkedin_result.summary_text) > 50)
            else ""
        )
        news_found = bool(li_summary and "No recent updates" not in li_summary)

        full_company_data = {
            "name": getattr(website_result, "name", domain),
            "content": {
                "value_proposition": current_val_prop,
                "solutions": getattr(website_result, "solutions", "N/A"),
                "industries": getattr(website_result, "industries", "N/A"),
            },
            "linkedin_update": li_summary or "No recent updates.",
            "last_updated": datetime.now().isoformat(),
        }

        if "Analysis currently unavailable" not in current_val_prop:
            memory[domain] = full_company_data

        if website_changed or news_found:
            full_company_data["has_changes"] = True
            updates_found.append(full_company_data)
            print(f"✅ Update found for {domain}")
        else:
            print(f"💤 No updates for {domain}")

        await asyncio.sleep(5)

    utils.save_memory(memory)
    print("💾 Memory updated.")

    if not updates_found:
        post_to_slack("No significant updates in the competitive environment today.")
        return

    all_findings = [
        f"{c['name']}: {c['content']['value_proposition']}" for c in updates_found
    ]
    summary_prompt = f"Act as a CMO. Write a 3-sentence summary of:\n{all_findings}"
    analyst_summary = await agent.run_agent_turn(summary_prompt, [], headless=False)

    pdf_bytes = utils.create_pdf(
        updates_found, analyst_summary, reference_company=REFERENCE_NAME
    )
    filename = f"Daily_Brief_{datetime.now().strftime('%Y-%m-%d')}.pdf"

    subscribers = (
        db.collection("subscribers")
        .where(filter=FieldFilter("status", "==", "active"))
        .stream()
    )
    for doc in subscribers:
        utils.send_email(
            f"Daily Brief - {datetime.now().strftime('%Y-%m-%d')}",
            doc.to_dict()["email"],
            f"Attached is your report.\n\nSummary:\n{analyst_summary}",
            pdf_bytes,
            filename,
        )

    post_to_slack(f"*Analyst Summary:*\n{analyst_summary}", pdf_bytes, filename)


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

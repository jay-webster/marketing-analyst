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
from linkedin_tracker import LinkedInTracker

load_dotenv()
REFERENCE_DOMAIN = "navistone.com"
REFERENCE_NAME = "NaviStone"
CACHE_COLLECTION = "discovery_cache"

# --- HELPER: DATABASE ---
try:
    project_id = os.getenv("PROJECT_ID")
    db = firestore.Client(project=project_id) if project_id else firestore.Client()
except Exception:
    db = None


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


# --- CORE LOGIC: DISCOVER ---
async def discover_competitors(target_domain):
    print(f"🔭 Starting Deep Discovery for {target_domain}...")

    if db:
        doc_ref = db.collection(CACHE_COLLECTION).document(target_domain)
        doc = doc_ref.get()
        if doc.exists:
            print(f"⚡ Cache Hit! Loading results for {target_domain}.")
            data = doc.to_dict()
            return data.get("competitors", [])

    print(f"🐢 Cache Miss. Running full analysis for {target_domain}...")

    prompt = (
        f"I need to identify the top 5 direct competitors for {target_domain}. "
        f"Do NOT guess based on the name.\n\n"
        f"STEP 1: Use `scrape_website` to analyze {target_domain}. Identify their specific industry.\n"
        f"STEP 2: Use `Google Search` to find 5 actual competitors in that industry.\n"
        f"SAFETY NET: If Search fails, use internal training data.\n"
        f"STEP 3: Return JSON with keys: 'industry_profile' (string) and 'competitors' (list of objects with name, domain, reason)."
    )

    try:
        raw_response = await agent.run_agent_turn(prompt, [], headless=True)
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            competitors = data.get("competitors", [])
            profile = data.get("industry_profile", "Unknown")

            if db and competitors:
                # Initialize with empty dismissed list
                db.collection(CACHE_COLLECTION).document(target_domain).set(
                    {
                        "industry_profile": profile,
                        "competitors": competitors,
                        "dismissed": [],
                        "last_updated": datetime.now(),
                    }
                )
            return competitors
        else:
            return []
    except Exception as e:
        print(f"❌ Discovery failed: {e}")
        return []


# --- CORE LOGIC: REFRESH (With Blacklist Support) ---
async def refresh_competitors(target_domain, target_count=5):
    print(f"🔄 Refreshing list for {target_domain}...")
    if not db:
        return []

    doc_ref = db.collection(CACHE_COLLECTION).document(target_domain)
    doc = doc_ref.get()

    existing_competitors = []
    dismissed_domains = []
    industry_profile = "a specific industry"

    if doc.exists:
        data = doc.to_dict()
        existing_competitors = data.get("competitors", [])
        dismissed_domains = data.get("dismissed", [])
        industry_profile = data.get("industry_profile", industry_profile)

    needed = target_count - len(existing_competitors)
    if needed <= 0:
        return existing_competitors

    # TRICK: Always ask for at least 3 to ensure we get results, then slice later.
    ask_for = max(needed, 3)

    print(f"🔍 Need {needed} (Asking for {ask_for}) new competitors...")

    current_names = [c["name"] for c in existing_competitors]
    current_domains = [c["domain"] for c in existing_competitors]
    dismissed_list = ", ".join(dismissed_domains) if dismissed_domains else "None"

    prompt = (
        f"I need {ask_for} NEW competitors for {target_domain} (Industry: {industry_profile}).\n"
        f"CURRENT LIST: {', '.join(current_names)}.\n"
        f"DISMISSED (DO NOT SUGGEST): {dismissed_list}.\n\n"
        f"STEP 1: Find {ask_for} high-quality alternatives that are NOT in the lists above.\n"
        f"STEP 2: Return JSON with key 'competitors' containing the new objects."
    )

    try:
        raw_response = await agent.run_agent_turn(prompt, [], headless=True)
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)

        if json_match:
            data = json.loads(json_match.group(0))
            candidates = data.get("competitors", [])

            valid_new_additions = []

            # Python Logic: Double-Check the Agent's work
            for cand in candidates:
                d = cand.get("domain", "")
                n = cand.get("name", "")

                # Check 1: Is it already in the list?
                if d in current_domains or n in current_names:
                    continue

                # Check 2: Was it dismissed?
                if d in dismissed_domains:
                    continue

                valid_new_additions.append(cand)

            # Slicing: Only take what we need to reach the target
            final_additions = valid_new_additions[:needed]

            if final_additions:
                full_list = existing_competitors + final_additions
                doc_ref.update(
                    {"competitors": full_list, "last_updated": datetime.now()}
                )
                print(f"✅ Added {len(final_additions)} competitors.")
                return full_list
            else:
                print(
                    "⚠️ Agent returned candidates, but they were all duplicates or dismissed."
                )
                return existing_competitors

        return existing_competitors

    except Exception as e:
        print(f"❌ Refresh failed: {e}")
        return existing_competitors


# --- CORE LOGIC: SURGICAL REMOVE (Blacklist Update) ---
def remove_competitor_from_cache(target_domain, competitor_domain_to_remove):
    """
    Removes a competitor AND adds them to the 'dismissed' blacklist.
    """
    if not db:
        return

    try:
        doc_ref = db.collection(CACHE_COLLECTION).document(target_domain)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            current_list = data.get("competitors", [])
            dismissed_list = data.get("dismissed", [])

            # 1. Remove from active list
            new_list = [
                c
                for c in current_list
                if c.get("domain") != competitor_domain_to_remove
            ]

            # 2. Add to Blacklist (avoid duplicates)
            if competitor_domain_to_remove not in dismissed_list:
                dismissed_list.append(competitor_domain_to_remove)

            # 3. Update DB
            doc_ref.update({"competitors": new_list, "dismissed": dismissed_list})
            print(f"🗑️ Blacklisted {competitor_domain_to_remove} for {target_domain}")
    except Exception as e:
        print(f"❌ Error updating cache: {e}")


# --- EXISTING HELPERS (Keep these) ---
async def check_linkedin_updates(company_name, domain):
    print(f"\n--- 🕵️‍♂️ Starting LinkedIn Check for {company_name} ---")
    tracker = LinkedInTracker(agent_module=agent, use_mock=False)
    try:
        return await tracker.get_company_updates(company_name, domain)
    except Exception:
        return None


async def analyze_competitor_website(domain):
    # (Same as your previous file - omitted for brevity, but KEEP IT in your file)
    # ... Use the code from the previous working version for analyze_competitor_website ...
    urls_to_try = [f"https://{domain}", f"https://www.{domain}"]
    for url in urls_to_try:
        try:
            analysis_prompt = (
                f"Analyze the website {url} using the scrape_website tool. "
                f"If the scrape returns empty or 'blocked', use your internal knowledge. "
                f"Return a JSON object with keys: 'name', 'value_proposition', 'solutions', 'industries'. "
            )
            raw_response = await agent.run_agent_turn(
                analysis_prompt, [], headless=True
            )
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                if data.get("value_proposition") not in ["N/A", "BLOCKED", None]:
                    return SimpleNamespace(**data)
        except Exception:
            pass

    try:
        fallback_prompt = f"Act as CMO. Profile '{domain}'. Return JSON keys: 'name', 'value_proposition', 'solutions', 'industries'."
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


async def run_daily_brief():
    # (Same as your previous file - omitted for brevity, but KEEP IT)
    # ... Use the code from the previous working version ...
    pass

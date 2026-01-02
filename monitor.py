import os
import asyncio
import agent
import utils
import json
import re
import ast
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


# --- CORE LOGIC: REFRESH (With Aggressive Retry) ---


async def refresh_competitors(target_domain, target_count=5, retry_level=0):
    print(f"🔄 Refreshing list for {target_domain} (Attempt: {retry_level})...")
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

    # Filter garbage out of existing
    existing_competitors = [
        c for c in existing_competitors if c.get("name") != "Unknown"
    ]

    needed = target_count - len(existing_competitors)
    if needed <= 0:
        return existing_competitors

    ask_for = max(needed, 3) + (retry_level * 2)

    current_names = [c["name"] for c in existing_competitors]
    current_domains_norm = [
        d.lower()
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .split("/")[0]
        for d in [c["domain"] for c in existing_competitors]
    ]
    dismissed_norm = [
        d.lower()
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "")
        .split("/")[0]
        for d in dismissed_domains
    ]

    banned_list = ", ".join(current_names)

    instruction_modifier = ""
    if retry_level > 0:
        instruction_modifier = "⚠️ PREVIOUS ATTEMPT FAILED. You used single quotes or missing keys. USE VALID JSON with double quotes. Find niche players."

    prompt = (
        f"I need {ask_for} NEW competitors for {target_domain} (Industry: {industry_profile}).\n"
        f"ALREADY LISTED (BANNED): {banned_list}.\n"
        f"{instruction_modifier}\n\n"
        f"INSTRUCTION: Find {ask_for} companies that are NOT in the BANNED list above.\n"
        f"You MUST return a JSON object with this EXACT schema:\n"
        f"{{ 'competitors': [ {{ 'name': 'Company Name', 'domain': 'company.com', 'reason': 'Why they match' }} ] }}\n"
        f"DO NOT use keys like 'company' or 'description'. YOU MUST FIND THE DOMAIN."
    )

    try:
        raw_response = await agent.run_agent_turn(prompt, [], headless=True)

        # --- BULLETPROOF PARSING LOGIC ---
        data = {}
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)

        if json_match:
            json_str = json_match.group(0)
            try:
                # Try standard JSON first
                data = json.loads(json_str)
            except json.JSONDecodeError:
                print("⚠️ JSON Error. Trying Python eval for single quotes...")
                try:
                    # Fallback: Handle single quotes (Python dict syntax)
                    data = ast.literal_eval(json_str)
                except Exception:
                    print("❌ Parsing failed completely.")
                    data = {}

        candidates = data.get("competitors", [])
        valid_new_additions = []

        for cand in candidates:
            # 1. Fix Schema Hallucinations
            if "company" in cand and "name" not in cand:
                cand["name"] = cand["company"]

            # 2. Fix Missing Domain (Guessing Strategy)
            if "domain" not in cand or not cand["domain"]:
                print(f"⚠️ Guessing domain for {cand.get('name')}")
                clean_name = (
                    cand.get("name", "").replace(" ", "").replace(",", "").lower()
                )
                cand["domain"] = f"{clean_name}.com"

            raw_domain = cand.get("domain", "").lower()

            # 3. Final Validation
            if not raw_domain or raw_domain == "unknown":
                continue

            norm_domain = (
                raw_domain.replace("https://", "")
                .replace("http://", "")
                .replace("www.", "")
                .split("/")[0]
            )

            if norm_domain in current_domains_norm:
                print(f"⚠️ Skipping duplicate: {raw_domain}")
                continue
            if norm_domain in dismissed_norm:
                print(f"⚠️ Skipping dismissed: {raw_domain}")
                continue
            if target_domain in raw_domain:
                continue

            valid_new_additions.append(cand)

        final_additions = valid_new_additions[:needed]

        if final_additions:
            full_list = existing_competitors + final_additions
            doc_ref.update({"competitors": full_list, "last_updated": datetime.now()})
            print(f"✅ Added {len(final_additions)} competitors.")
            return full_list
        else:
            print("⚠️ All candidates were filtered out.")
            if retry_level < 2:
                print(f"🔄 Triggering retry level {retry_level + 1}...")
                return await refresh_competitors(
                    target_domain, target_count, retry_level=retry_level + 1
                )

            return existing_competitors

    except Exception as e:
        print(f"❌ Refresh failed: {e}")
        return existing_competitors


# --- CORE LOGIC: SURGICAL REMOVE ---
def remove_competitor_from_cache(target_domain, competitor_domain_to_remove):
    if not db:
        return

    try:
        doc_ref = db.collection(CACHE_COLLECTION).document(target_domain)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            current_list = data.get("competitors", [])
            dismissed_list = data.get("dismissed", [])

            # Remove from active
            new_list = [
                c
                for c in current_list
                if c.get("domain") != competitor_domain_to_remove
            ]

            # Add to dismissed
            if competitor_domain_to_remove not in dismissed_list:
                dismissed_list.append(competitor_domain_to_remove)

            doc_ref.update({"competitors": new_list, "dismissed": dismissed_list})
            print(f"🗑️ Blacklisted {competitor_domain_to_remove} for {target_domain}")
    except Exception as e:
        print(f"❌ Error updating cache: {e}")


# --- EXISTING HELPER FUNCTIONS ---
async def check_linkedin_updates(company_name, domain):
    print(f"\n--- 🕵️‍♂️ Starting LinkedIn Check for {company_name} ---")
    tracker = LinkedInTracker(agent_module=agent, use_mock=False)
    try:
        return await tracker.get_company_updates(company_name, domain)
    except Exception:
        return None


async def analyze_competitor_website(domain):
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
    print(f"🚀 Starting Daily Brief: {datetime.now()}")
    comp_docs = db.collection("competitors").stream()
    competitors = [doc.id for doc in comp_docs]
    memory = utils.load_memory()

    if not competitors:
        competitors = ["pebblepost.com"]
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
        if (prev_val_prop != current_val_prop) and (
            "Analysis currently unavailable" not in current_val_prop
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

    try:
        subscribers = (
            db.collection("subscribers").where("status", "==", "active").stream()
        )
        for doc in subscribers:
            utils.send_email(
                f"Daily Brief - {datetime.now().strftime('%Y-%m-%d')}",
                doc.to_dict()["email"],
                f"Summary:\n{analyst_summary}",
                pdf_bytes,
                filename,
            )
    except Exception:
        pass
    post_to_slack(f"*Analyst Summary:*\n{analyst_summary}", pdf_bytes, filename)


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

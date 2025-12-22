import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import asyncio
import agent
import utils
from datetime import datetime


async def run_daily_brief():
    print(f"🚀 Starting Daily Brief: {datetime.now()}")

    # 1. SETUP
    competitors = utils.get_competitors()
    memory = utils.load_memory()

    full_report_text = f"# Daily Competitive Intelligence Brief\n\n"

    # We will build a single string for the Slack "Cover Letter"
    slack_summary_text = f"🚀 *Daily Intel: {datetime.now().strftime('%Y-%m-%d')}*\n\n"

    for domain in competitors:
        print(f"--- Analyzing {domain} ---")

        is_first_run = domain not in memory

        if is_first_run:
            print(f"🆕 First run for {domain}.")
            prompt = (
                f"Deep dive analysis of {domain}. \n"
                f"Create a Baseline Strategic Profile focusing on: \n"
                f"1. Core Product Features.\n"
                f"2. Strategic Messaging.\n"
                f"3. Recent Case Studies.\n"
                f"Do NOT use the word 'New' unless explicitly dated in the last 30 days."
            )
        else:
            print(f"🔄 Updating {domain}.")
            prompt = (
                f"Deep dive analysis of {domain}. \n"
                f"Focus strictly on UPDATES since the last scan: \n"
                f"1. New Product Features.\n"
                f"2. Strategic Messaging changes.\n"
                f"3. New Case Studies.\n"
                f"If nothing new is found, explicitly state 'No significant updates detected.'"
            )

        try:
            report_part = await agent.run_agent_turn(
                prompt, chat_history=[], headless=True
            )

            # Save to Memory & PDF Report
            memory[domain] = {
                "last_scan": datetime.now().strftime("%Y-%m-%d"),
                "latest_summary": report_part[:200] + "...",
            }
            full_report_text += f"# Report: {domain}\n\n{report_part}\n\n"

            # Add to Slack Cover Letter
            # Icon Logic
            icon = "🟢"
            if "New Product" in report_part or "Pricing" in report_part:
                icon = "🔴"  # Alert
            elif "No significant updates" in report_part:
                icon = "⚪"

            slack_summary_text += f"{icon} *{domain}*\n"

        except Exception as e:
            print(f"❌ Failed {domain}: {e}")
            full_report_text += f"# Report: {domain}\n\nError: {e}\n\n"
            slack_summary_text += f"⚠️ *{domain}*: Error analyzing site.\n"

    # 2. SAVE MEMORY
    utils.save_memory(memory)

    # 3. GENERATE PDF
    print("📝 Generating PDF...")
    try:
        pdf_bytes = utils.create_pdf(full_report_text)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"Daily_Brief_{date_str}.pdf"

        # 4. SEND EMAIL
        print("📧 Sending Email...")
        utils.send_email(
            pdf_bytes, filename, subject=f"Daily Intelligence Brief: {date_str}"
        )

        # 5. UPLOAD TO SLACK (New!)
        print("💬 Uploading to Slack...")
        slack_summary_text += "\n📄 *See attached PDF for full details.*"
        utils.send_slack_file(pdf_bytes, filename, slack_summary_text)

    except Exception as e:
        print(f"❌ Output Failed: {e}")


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

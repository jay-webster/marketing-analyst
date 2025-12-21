import asyncio
import agent
import utils
from datetime import datetime

# 1. Your Watchlist
COMPETITORS = [
    "pebblepost.com",
    "lob.com",
    "postie.com",
    "heypoplar.com",
    "lsdirect.com",
    "postpilot.com",
]


async def run_daily_brief():
    print(f"🚀 Starting Daily Brief: {datetime.now()}")

    # Initialize the Master Report with a Main Title
    full_report_text = f"# Daily Competitive Intelligence Brief\n\n"

    for domain in COMPETITORS:
        print(f"--- Analyzing {domain} ---")

        # 2. Run the Agent (Headless)
        prompt = f"Analyze {domain}. Focus on any new product launches, pricing changes, or press releases found on the homepage."

        try:
            # Get the raw text analysis
            report_part = await agent.run_agent_turn(
                prompt, chat_history=[], headless=True
            )

            # Format: Add a clear Title for this section
            section_header = f"# Report: {domain}\n"

            # Append to master report
            # We add "\n\n" to ensure spacing
            full_report_text += f"{section_header}\n{report_part}\n\n"

            print(f"✅ Finished {domain}")

        except Exception as e:
            print(f"❌ Failed to analyze {domain}: {e}")
            full_report_text += f"# Report: {domain}\n\nError analyzing site: {e}\n\n"

    # 3. Create ONE Consolidated PDF
    print("📝 Generating Master PDF...")
    try:
        # Generate PDF from the accumulated text
        pdf_bytes = utils.create_pdf(full_report_text)

        # 4. Email ONE Master Report
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"Daily_Brief_{date_str}.pdf"

        print(f"📤 Sending Consolidated Brief ({len(COMPETITORS)} companies)...")
        utils.send_email(
            pdf_bytes, filename, subject=f"Daily Intelligence Brief: {date_str}"
        )

    except Exception as e:
        print(f"❌ Failed to generate/send master PDF: {e}")


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

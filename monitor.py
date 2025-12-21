import asyncio
import agent
import utils
from datetime import datetime

# 1. Your Watchlist
COMPETITORS = [
    "pebblepost.com",
    "lob.com",
    "heypoplar.com",
    "lsdirect.com",
    "postpilot.com",
    # Add more domains here as you grow
]


async def run_daily_brief():
    print(f"🚀 Starting Daily Brief: {datetime.now()}")

    for domain in COMPETITORS:
        print(f"--- Analyzing {domain} ---")

        # 2. Run the Agent (Headless)
        prompt = f"Analyze {domain}. Focus on any new product launches or press releases found on the homepage."

        try:
            report_text = await agent.run_agent_turn(
                prompt, chat_history=[], headless=True
            )

            # 3. Create PDF
            pdf_bytes = utils.create_pdf(report_text)
            filename = f"Report_{domain}_{datetime.now().strftime('%Y-%m-%d')}.pdf"

            # 4. Email it!
            print("📤 Sending email...")
            utils.send_email(pdf_bytes, filename, subject=f"Strategy Update: {domain}")

        except Exception as e:
            print(f"❌ Failed to analyze {domain}: {e}")


if __name__ == "__main__":
    asyncio.run(run_daily_brief())

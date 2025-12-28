import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
import traceback
import agent


@dataclass
class LinkedInResult:
    company: str
    summary_text: str
    source_url: str
    found_at: str

    def to_dict(self):
        return asdict(self)


class LinkedInTracker:
    def __init__(self, agent_module, use_mock=False):
        self.agent = agent_module
        self.use_mock = use_mock

    async def get_company_updates(self, company_name, domain):
        if self.use_mock:
            return LinkedInResult(
                company=company_name,
                summary_text=f"MOCK: {company_name} posted update.",
                source_url="http://mock",
                found_at=datetime.now().isoformat(),
            )

        print(f"🔍 [LinkedIn] Searching indexed updates for {company_name}...")

        researcher_instruction = (
            "You are a master researcher. Find public news and social media summaries using Google Search. "
            "Do NOT output JSON. Output clear text summaries."
        )

        prompt = (
            f"Use the Google Search tool immediately to find information about '{company_name}' (associated with domain '{domain}').\n"  # <--- Added context
            f"Queries to run:\n"
            f"1. 'site:linkedin.com/company/{domain.split('.')[0]} recent posts'\n"
            f"2. '{company_name} {domain} news press release {datetime.now().year}'\n"  # <--- Added domain here
            f"3. '{company_name} blog updates'\n\n"
            f"Output Requirement:\n"
            f"- Do NOT tell me what you are going to do.\n"
            f"- Run the search tool first.\n"
            f"- After searching, summarize 3 specific findings (hiring, products, or news) from the last 90 days.\n"
            f"- If no specific dates are found, summarize the company's core value proposition based on the search snippets."
        )

        try:
            # PASS THE NEW ARGUMENT: toolset="search_only"
            response_text = await self.agent.run_agent_turn(
                user_prompt=prompt,
                chat_history=[],
                headless=False,
                system_instruction=researcher_instruction,
                toolset="search_only",  # <--- CRITICAL FIX
            )

            return LinkedInResult(
                company=company_name,
                summary_text=response_text,
                source_url=f"https://www.google.com/search?q=site:linkedin.com/company/{domain}",
                found_at=datetime.now().isoformat(),
            )

        except Exception as e:
            print(f"❌ LinkedIn Tracker Error: {e}")
            traceback.print_exc()
            return LinkedInResult(
                company=company_name,
                summary_text="Error retrieving updates.",
                source_url="N/A",
                found_at=datetime.now().isoformat(),
            )


if __name__ == "__main__":

    async def test():
        # Ensure use_mock is False to test real search
        tracker = LinkedInTracker(agent, use_mock=False)
        result = await tracker.get_company_updates("NaviStone", "navistone.com")
        print("\n--- FINAL RESULT ---")
        print(result)

    asyncio.run(test())

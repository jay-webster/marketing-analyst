import os
import asyncio
import json
import re
from datetime import datetime


class LinkedInTracker:
    def __init__(self, agent_module, use_mock=False):
        self.agent = agent_module
        self.use_mock = use_mock

    async def get_company_updates(self, company_name, domain):
        """
        Fetches recent LinkedIn posts/news for a company using the Agent.
        """
        if self.use_mock:
            return None  # Skip mock logic for prod

        print(f"🔍 [LinkedIn] Searching indexed updates for {company_name}...")

        prompt = (
            f"Search for recent LinkedIn posts, news, or press releases from the official account of {company_name} ({domain}). "
            f"Focus on the last 30 days. "
            f"Summarize 1-2 key strategic updates (new products, partnerships, executive hires). "
            f"If nothing relevant is found, return 'No recent updates'."
        )

        try:
            # FIX: Use positional arguments to match agent.py signature
            # (query, history, headless)
            response_text = await self.agent.run_agent_turn(prompt, [], headless=True)

            return type(
                "LinkedInUpdate",
                (object,),
                {
                    "summary_text": response_text,
                    "url": f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}",
                },
            )()

        except Exception as e:
            print(f"❌ LinkedIn Tracker Error: {e}")
            return None

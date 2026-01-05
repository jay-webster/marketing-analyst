import os
import requests
import time
import random
from google import genai
from google.genai import types
from dotenv import load_dotenv
from googlesearch import search

load_dotenv()

# --- CONFIGURATION ---
# Use the stable Gemini 2.0 Flash model
MODEL_ID = "gemini-2.0-flash"
JINA_API_KEY = os.getenv("JINA_API_KEY", "")

# --- TOOLS ---


def scrape_website(url: str) -> str:
    """
    Scrapes a website using Jina Reader to get clean, LLM-friendly text.
    Handles JavaScript rendering and bypasses many simple bot blockers.
    """
    print(f"🛠️ Tool: Scraping {url}...")

    # Random delay to act like a human
    time.sleep(random.uniform(2, 4))

    jina_url = f"https://r.jina.ai/{url}"

    if not jina_url.startswith("https://"):
        return "Error: Only HTTPS URLs are supported."

    headers = {}
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"

    try:
        response = requests.get(jina_url, headers=headers, timeout=30, verify=True)
        if response.status_code == 200:
            return response.text[:15000]
        else:
            return f"Error: Failed to scrape {url}. Status: {response.status_code}"
    except Exception as e:
        return f"Error: Could not scrape website. Details: {e}"


def google_search(query: str) -> str:
    """
    Performs a Google Search and returns the top 5 results.
    Includes RETRY logic: loops up to 3 times if rate-limited.
    """
    print(f"🛠️ Tool: Searching Google for '{query}'...")

    max_retries = 3
    base_wait = 5  # Wait 5s, then 10s, then 15s...

    for attempt in range(max_retries):
        try:
            # Random throttle per attempt
            time.sleep(random.uniform(3, 6))

            results = []
            search_generator = search(query, num_results=5, advanced=True)

            for res in search_generator:
                results.append(
                    f"Title: {res.title}\nURL: {res.url}\nSnippet: {res.description}\n---"
                )

            if not results:
                return "No results found."

            return "\n".join(results)

        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "too many requests" in error_msg:
                wait_time = base_wait * (attempt + 1) + random.uniform(1, 3)
                print(
                    f"⚠️ Rate Limit (429). Retrying in {wait_time:.1f}s... (Attempt {attempt+1}/{max_retries})"
                )
                time.sleep(wait_time)
                continue  # Loops back to try search() again

            # If it's a different error, fail immediately
            return f"Error performing Google Search: {e}"

    return "Error: Google Search failed after multiple retries due to rate limits."


# --- MAIN AGENT LOGIC ---


async def run_agent_turn(prompt: str, history: list = [], headless: bool = True):
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    tools = [scrape_website, google_search]

    try:
        # 1. Ask Model
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(tools=tools, temperature=0.3),
        )
    except Exception as e:
        return f"LLM Connection Error: {e}"

    # 2. Check for Function Calls
    if not response.function_calls:
        return response.text

    # 3. Execute Tools
    tool_outputs = []
    for call in response.function_calls:
        func_name = call.name
        func_args = call.args

        if func_name == "scrape_website":
            output = scrape_website(func_args["url"])
        elif func_name == "google_search":
            output = google_search(func_args["query"])
        else:
            output = "Error: Unknown tool."

        tool_outputs.append(
            types.Part.from_function_response(
                name=func_name, response={"result": output}
            )
        )

    # 4. Synthesize Answer
    parts = [types.Part.from_text(text=prompt)]
    if response.candidates:
        parts.append(response.candidates[0].content.parts[0])
    parts.extend(tool_outputs)

    try:
        final_response = client.models.generate_content(
            model=MODEL_ID, contents=[types.Content(role="user", parts=parts)]
        )
        return final_response.text
    except Exception as e:
        return f"Error generating final response: {e}"

import os
import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv
from googlesearch import search

load_dotenv()

# --- CONFIGURATION ---
MODEL_ID = "gemini-2.5-flash"  # Or "gemini-1.5-flash"
JINA_API_KEY = os.getenv("JINA_API_KEY", "")  # Optional, but good for rate limits

# --- TOOLS ---


def scrape_website(url: str) -> str:
    """
    Scrapes a website using Jina Reader to get clean, LLM-friendly text.
    Handles JavaScript rendering and bypasses many simple bot blockers.
    """
    print(f"🛠️ Tool: Scraping {url}...")

    # Use Jina Reader (free tier is generous, no key needed for basic use)
    jina_url = f"https://r.jina.ai/{url}"

    # Security: Ensure HTTPS only
    if not jina_url.startswith("https://"):
        return "Error: Only HTTPS URLs are supported for security reasons."

    headers = {}
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"

    try:
        # Security: Explicit SSL verification enabled
        response = requests.get(jina_url, headers=headers, timeout=30, verify=True)
        if response.status_code == 200:
            return response.text[:15000]  # Return first 15k chars to save context
        else:
            return f"Error: Failed to scrape {url}. Status: {response.status_code}"
    except Exception as e:
        return f"Error: Could not scrape website. Details: {e}"


def google_search(query: str) -> str:
    """
    Performs a Google Search and returns the top 5 results with snippets.
    Useful for finding competitors, news, or verifying domain names.
    """
    print(f"🛠️ Tool: Searching Google for '{query}'...")
    results = []
    try:
        # advanced=True returns objects with title, description, and url
        search_results = search(query, num_results=5, advanced=True)
        for res in search_results:
            results.append(
                f"Title: {res.title}\nURL: {res.url}\nSnippet: {res.description}\n---"
            )

        return "\n".join(results)
    except Exception as e:
        return f"Error performing Google Search: {e}"


# --- MAIN AGENT LOGIC ---


async def run_agent_turn(prompt: str, history: list = [], headless: bool = True):
    """
    Executes a single turn of the agent:
    1. Sends prompt + tools to Gemini.
    2. Executes any tools Gemini calls.
    3. Sends tool outputs back to Gemini for the final answer.
    """
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    # Define available tools
    tools = [scrape_website, google_search]

    # 1. First Call: Ask the model what it wants to do
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=tools, temperature=0.3  # Keep it analytical
            ),
        )
    except Exception as e:
        return f"LLM Error: {e}"

    # 2. Check for Function Calls
    if not response.function_calls:
        # Model answered directly without tools
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

        # Add to the conversation for the next turn
        tool_outputs.append(
            types.Part.from_function_response(
                name=func_name, response={"result": output}
            )
        )

    # 4. Final Call: Send tool outputs back to model to synthesize the answer
    # We need to reconstruct the chat history for this turn
    parts = [types.Part.from_text(text=prompt)]

    # Add the model's function call request
    parts.append(response.candidates[0].content.parts[0])

    # Add our function responses
    parts.extend(tool_outputs)

    final_response = client.models.generate_content(
        model=MODEL_ID, contents=[types.Content(role="user", parts=parts)]
    )

    return final_response.text

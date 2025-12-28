from fastmcp import FastMCP
import requests
import traceback

# 1. Initialize the Server
mcp = FastMCP("marketing-scraper")


# 2. Define the Scraping Tool (Powered by Jina.ai)
@mcp.tool()
def scrape_website(url: str) -> str:
    """
    Visits a website and returns its text content formatted for AI.
    Uses Jina Reader to handle complex sites and blockers.
    """
    print(f"🕵️‍♂️ Scraper visiting: {url}")

    # We prefix the URL with https://r.jina.ai/ to use their free reader API
    jina_url = f"https://r.jina.ai/{url}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        response = requests.get(jina_url, headers=headers, timeout=20)

        if response.status_code != 200:
            return f"Error: Failed to access {url}. Status code: {response.status_code}"

        text = response.text

        # Limit length to prevent context overflow (approx 8000 chars)
        return text[:8000]

    except Exception as e:
        print(f"❌ Scraping error: {e}")
        return f"Error scraping {url}: {str(e)}"


# 3. Define a Helper Tool (Ping)
@mcp.tool()
def ping() -> str:
    """Checks if the server is alive."""
    return "pong - server is ready"


# 4. Start the Server (SSE Mode)
if __name__ == "__main__":
    print("🚀 Starting Marketing Scraper Server (Jina Edition) on port 8000...")
    mcp.run(transport="sse", port=8000, host="0.0.0.0")

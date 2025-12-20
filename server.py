from fastmcp import FastMCP
import httpx
from bs4 import BeautifulSoup
import asyncio
import os

# Initialize
mcp = FastMCP("marketing-analyst")

# Constants
USER_AGENT = "marketing-analyst/1.0 (bot@example.com)"

async def make_request(url: str):
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            return await client.get(url, headers=headers)
        except Exception:
            return None

def parse_html_blocking(html_content):
    """
    Standard BeautifulSoup parsing.
    Running this with 2GB RAM is perfectly safe.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove junk
    for element in soup(["script", "style", "nav", "footer", "iframe", "svg"]):
        element.decompose()
        
    text = soup.get_text()
    
    # Clean whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    clean_text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return clean_text[:12000]

@mcp.tool()
async def analyze_website(url: str) -> str:
    """Visits a website and extracts text."""
    if not url.startswith("http"):
        url = "https://" + url
        
    print(f"🕵️‍♀️ Visiting: {url}")
    response = await make_request(url)
    
    if not response:
        return f"Error: Could not reach {url}."
        
    # Run in a thread so we don't block the heartbeat
    clean_text = await asyncio.to_thread(parse_html_blocking, response.text)
    
    return f"--- CONTENT FOR {url} ---\n{clean_text}\n--- END ---"

if __name__ == "__main__":
    mcp.run(transport='sse', host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
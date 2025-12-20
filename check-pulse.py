import httpx
import asyncio

# 🔴 PASTE YOUR BACKEND URL HERE (Make sure it ends in /sse)
# Example: "https://marketing-mcp-xyz.run.app/sse"
BACKEND_URL = "https://marketing-frontend-4v4sc3n5qq-uc.a.run.app/sse"

async def check_health():
    print(f"🩺 Checking pulse of: {BACKEND_URL}")
    
    # We send a standard GET request. 
    # Even if it's an SSE endpoint, it should respond (even with a 405 or 404).
    # If it times out or refuses connection, the server is DEAD.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(BACKEND_URL)
            print(f"✅ RESPONSE RECEIVED: Status Code {response.status_code}")
            print("🎉 The Backend is ALIVE and reachable.")
    except Exception as e:
        print(f"💀 CONNECTION FAILED: {e}")
        print("➡️ This means the Backend crashed on startup.")

if __name__ == "__main__":
    asyncio.run(check_health())
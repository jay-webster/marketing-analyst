import asyncio, os, json, re
from google import genai
from google.genai import types
from pydantic import BaseModel
from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_SERVER_URL = "https://marketing-mcp-4v4sc3n5qq-uc.a.run.app/sse"
PROJECT_ID = "marketing-analyst-prod"


class CompetitorAnalysis(BaseModel):
    name: str = "Unknown"
    value_proposition: str = "N/A"
    solutions: str = "N/A"
    industries: str = "N/A"
    has_changes: bool = True


def ensure_string(val):
    """Safely converts lists or objects from the AI into flat strings."""
    if isinstance(val, list):
        return ", ".join(str(i) for i in val)
    return str(val)


async def run_agent_turn(user_prompt, chat_history, headless=False):
    async with sse_client(MCP_SERVER_URL, timeout=300) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = await session.list_tools()
            gemini_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema,
                }
                for t in tools.tools
            ]
            client = genai.Client(
                vertexai=True, project=PROJECT_ID, location="us-central1"
            )

            config = types.GenerateContentConfig(
                system_instruction="You are a marketing analyst. Scrape the site and provide a JSON block with keys: name, value_proposition, solutions, industries, has_changes.",
                tools=[types.Tool(function_declarations=gemini_tools)],
                temperature=0.0,
            )

            chat = client.chats.create(model="gemini-2.0-flash", config=config)
            response = chat.send_message(user_prompt)

            if response.candidates[0].content.parts[0].function_call:
                fn = response.candidates[0].content.parts[0].function_call
                tool_output = await execute_tool(session, fn)
                response = chat.send_message(
                    [
                        types.Part.from_function_response(
                            name=fn.name, response={"result": tool_output}
                        ),
                        types.Part.from_text(
                            text="I have the data. Output the JSON block now."
                        ),
                    ]
                )

            if headless:
                text = response.text
                try:
                    match = re.search(r"(\{.*?\})", text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                        # Use ensure_string to prevent validation errors
                        return CompetitorAnalysis(
                            name=ensure_string(data.get("name", "Unknown")),
                            value_proposition=ensure_string(
                                data.get("value_proposition", "N/A")
                            ),
                            solutions=ensure_string(data.get("solutions", "N/A")),
                            industries=ensure_string(data.get("industries", "N/A")),
                            has_changes=True,
                        )
                except Exception as e:
                    print(f"DEBUG: Extraction failed: {e}")
                return CompetitorAnalysis(
                    name="Extraction Error", value_proposition="Failed to parse"
                )

            return response.text


async def execute_tool(session, fn):
    try:
        args = dict(fn.args)
        if "url" in args and not args["url"].startswith("http"):
            args["url"] = f"https://{args['url']}"
        result = await session.call_tool(fn.name, args)
        return result.content[0].text if result.content else "No content found."
    except Exception as e:
        return f"Tool Error: {str(e)}"

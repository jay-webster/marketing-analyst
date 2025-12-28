import os
import asyncio
import traceback
import json
from dotenv import load_dotenv

# Google Gen AI SDK
from google import genai
from google.genai import types

# MCP Imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

load_dotenv()

# Configuration
MCP_SERVER_URL = "http://127.0.0.1:8000/sse"
PROJECT_ID = os.getenv("PROJECT_ID", "marketing-analyst-prod")
os.environ["NO_PROXY"] = "localhost,127.0.0.1"


async def run_agent_turn(
    user_prompt,
    chat_history,
    headless=False,
    system_instruction=None,
    toolset="default",
):
    """
    Runs a single turn of the agent with automatic retries for connection stability.
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            return await _execute_turn(
                user_prompt, chat_history, system_instruction, toolset
            )
        except Exception as e:
            # If it's the last attempt, fail loudly
            if attempt == max_retries - 1:
                print(f"\n❌ Agent failed after {max_retries} attempts: {e}")
                return f"Agent execution failed: {str(e)}"

            # Otherwise, print a small warning and retry
            print(
                f"⚠️ Connection glitch (attempt {attempt+1}/{max_retries}). Retrying..."
            )
            await asyncio.sleep(2)


async def _execute_turn(user_prompt, chat_history, system_instruction, toolset):
    if system_instruction is None:
        system_instruction = "You are a marketing analyst. Provide helpful responses."

    async with sse_client(MCP_SERVER_URL, timeout=300) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()

            # 1. Fetch Tools
            tools = await session.list_tools()

            # Convert MCP tools to Gemini Function Declarations
            mcp_functions = []
            for t in tools.tools:
                mcp_functions.append(
                    types.FunctionDeclaration(
                        name=t.name, description=t.description, parameters=t.inputSchema
                    )
                )

            # 2. DECIDE WHICH TOOLSET TO USE
            active_tools = []
            if toolset == "search_only":
                active_tools = [types.Tool(google_search=types.GoogleSearch())]
            else:
                active_tools = [types.Tool(function_declarations=mcp_functions)]

            # 3. Configure Gemini
            client = genai.Client(
                vertexai=True, project=PROJECT_ID, location="us-central1"
            )

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=active_tools,
                temperature=0.0,
            )

            # Use Stable Model
            chat = client.chats.create(model="gemini-2.0-flash-001", config=config)

            response = chat.send_message(user_prompt)

            # --- 4. THE TOOL EXECUTION LOOP ---
            while True:
                # Case A: Model returned text (We are done)
                if response.text:
                    return response.text

                # Case B: Model wants to call a function
                try:
                    part = response.candidates[0].content.parts[0]
                except:
                    return "Error: Empty response from model."

                if part.function_call:
                    fn_name = part.function_call.name
                    fn_args = part.function_call.args

                    print(f"⚙️ Agent executing tool: {fn_name}...")

                    # Execute the tool on the MCP Server
                    result = await session.call_tool(fn_name, arguments=fn_args)

                    # Send the result back to Gemini
                    response = chat.send_message(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fn_name, response={"result": result.content}
                            )
                        )
                    )
                else:
                    return "No text returned from model (and no tool called)."


if __name__ == "__main__":
    asyncio.run(run_agent_turn("Hello", []))

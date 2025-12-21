# agent.py
import asyncio
import os
import streamlit as st
from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.sse import sse_client

# Configuration
MCP_SERVER_URL = "https://marketing-mcp-4v4sc3n5qq-uc.a.run.app/sse"
PROJECT_ID = os.popen("gcloud config get-value project").read().strip()
LOCATION = "us-central1"


async def run_agent_turn(user_prompt, chat_history):
    """
    Runs the agent logic.
    Note: We pass 'chat_history' in as an argument now,
    so this function doesn't depend directly on st.session_state.
    """
    async with sse_client(MCP_SERVER_URL, timeout=300) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()

            tools_list = await session.list_tools()
            gemini_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema,
                }
                for t in tools_list.tools
            ]

            # Build Gemini History from the passed chat_history
            gemini_history = []
            for msg in chat_history[:-1]:
                if msg.get("content"):
                    role = "user" if msg["role"] == "user" else "model"
                    gemini_history.append(
                        types.Content(
                            role=role, parts=[types.Part.from_text(text=msg["content"])]
                        )
                    )

            client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
            chat = client.chats.create(
                model="gemini-2.0-flash",
                history=gemini_history,
                config=types.GenerateContentConfig(
                    system_instruction="""
                    You are a Senior Marketing Strategist.
                    RULES:
                    - ALWAYS usage 'analyze_website' when the user provides a URL.
                    - URL SANITIZATION: If a user or tool provides a domain (e.g., 'example.com'), ALWAYS prepend 'https://' before calling the tool.
                    - Format your output with clear headers (##) and bullet points.
                    """,
                    tools=[types.Tool(function_declarations=gemini_tools)],
                ),
            )

            response = chat.send_message(user_prompt)

            # Tool Execution Loop
            while True:
                call_parts = [
                    p for p in response.candidates[0].content.parts if p.function_call
                ]
                if not call_parts:
                    break

                function_responses = []
                with st.status(f"🕵️‍♀️ Agent is working...", expanded=True) as status:
                    for part in call_parts:
                        fn = part.function_call
                        st.write(f"Executing: {fn.name}")
                        try:
                            # Auto-fix URLs
                            tool_args = dict(fn.args)
                            if "url" in tool_args and isinstance(tool_args["url"], str):
                                if not tool_args["url"].startswith(
                                    ("http://", "https://")
                                ):
                                    tool_args["url"] = f"https://{tool_args['url']}"
                                    st.caption(
                                        f"🔧 Auto-corrected URL to: {tool_args['url']}"
                                    )

                            result = await session.call_tool(
                                fn.name, arguments=tool_args
                            )
                            tool_output = result.content[0].text
                        except Exception as e:
                            tool_output = f"Error executing tool: {str(e)}"
                            st.write(f"🔍 Debug: {tool_output}")

                        function_responses.append(
                            types.Part.from_function_response(
                                name=fn.name, response={"result": tool_output}
                            )
                        )
                    status.update(
                        label="✅ Tools Completed", state="complete", expanded=False
                    )

                response = chat.send_message(function_responses)

            return response.text

import asyncio
import os
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from mcp import ClientSession
from mcp.client.sse import sse_client

# Configuration
MCP_SERVER_URL = "https://marketing-mcp-4v4sc3n5qq-uc.a.run.app/sse"

# FIX: Use environment variable for Project ID to avoid "gcloud not found" error
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "marketing-analyst-prod")
LOCATION = "us-central1"


# --- DATA STRUCTURE FOR PDF ---
class CompetitorAnalysis(BaseModel):
    """Schema for structured competitive analysis reports."""

    name: str = Field(description="The clean name of the competitor (e.g. PebblePost)")
    value_proposition: str = Field(
        description="The primary value proposition or headline"
    )
    solutions: str = Field(description="Key products, services, or solutions offered")
    industries: str = Field(description="Primary industries or verticals targeted")
    has_changes: bool = Field(
        description="True if the website content appears to have new or significant updates"
    )


async def run_agent_turn(user_prompt, chat_history, headless=False):
    """
    Runs the agent.
    - If headless=False: Returns STR (Chat mode with UI updates)
    - If headless=True: Returns OBJECT (Structured Pydantic model for PDF)
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

            # Build Gemini History
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

            # --- DYNAMIC CONFIGURATION ---
            if headless:
                # PDF MODE: Strict extraction logic
                sys_instruction = """
                You are a Competitive Intelligence Data Extractor.
                
                STEP-BY-STEP:
                1. Call 'analyze_website' for the provided URL.
                2. Based on the tool's findings, generate the report.
                3. If 'PREVIOUS ANALYSIS' exists, compare it to detect 'has_changes'.
                4. Output ONLY the JSON matching the schema.
                
                CRITICAL: You are in a structured pipeline. Do not talk. Do not explain. 
                Output the valid JSON immediately after the tool response.
                """
                config = types.GenerateContentConfig(
                    system_instruction=sys_instruction,
                    tools=[types.Tool(function_declarations=gemini_tools)],
                    response_mime_type="application/json",
                    response_schema=CompetitorAnalysis,
                )
            else:
                # CHAT MODE: Standard text output
                sys_instruction = """
                You are a Senior Marketing Strategist.
                CORE RULES:
                1. ANALYSIS MODE: If the user provides a URL, ALWAYS use 'analyze_website'.
                   - URL SANITIZATION: Always prepend 'https://' to domains.
                2. CONVERSATION MODE: If the user asks a follow-up, use existing context.
                3. FORMATTING: Format your output with clear headers (##) and bullet points.
                """
                config = types.GenerateContentConfig(
                    system_instruction=sys_instruction,
                    tools=[types.Tool(function_declarations=gemini_tools)],
                )

            # Initialize Chat
            chat = client.chats.create(
                model="gemini-2.0-flash",
                history=gemini_history,
                config=config,
            )

            response = chat.send_message(user_prompt)

            # Tool Execution Loop
            max_iterations = 5 if headless else 10
            iterations = 0

            while iterations < max_iterations:
                call_parts = [
                    p for p in response.candidates[0].content.parts if p.function_call
                ]
                if not call_parts:
                    break

                iterations += 1
                function_responses = []

                if not headless:
                    # UI MODE: Show status spinners
                    with st.status(f"🕵️‍♀️ Agent is working...", expanded=True) as status:
                        for part in call_parts:
                            fn = part.function_call
                            st.write(f"Executing: {fn.name}")
                            tool_output = await execute_tool(session, fn, headless)
                            function_responses.append(
                                types.Part.from_function_response(
                                    name=fn.name, response={"result": tool_output}
                                )
                            )
                        status.update(
                            label="✅ Tools Completed", state="complete", expanded=False
                        )
                else:
                    # SILENT MODE: Just do the work
                    for part in call_parts:
                        fn = part.function_call
                        print(f"Executing (Silent): {fn.name}")
                        tool_output = await execute_tool(session, fn, headless)
                        print(f"DEBUG: Tool Output Length: {len(tool_output)}")
                        function_responses.append(
                            types.Part.from_function_response(
                                name=fn.name, response={"result": tool_output}
                            )
                        )

                # Send tool outputs back to model
                response = chat.send_message(function_responses)

            if iterations >= max_iterations:
                print(f"⚠️ Warning: Agent reached max iterations ({max_iterations})")

            # --- RETURN LOGIC ---
            # --- RETURN LOGIC ---
            if headless:
                # Return the structured object (Pydantic)
                if response.parsed:
                    return response.parsed
                else:
                    # Attempt manual JSON extraction (Fallback for when SDK parsing fails)
                    import json

                    try:
                        # Safety check for empty text
                        if (
                            not response
                            or not hasattr(response, "text")
                            or not response.text
                        ):
                            raise ValueError("Response text is empty/None")

                        clean_text = (
                            response.text.strip()
                            .replace("```json", "")
                            .replace("```", "")
                            .strip()
                        )
                        data = json.loads(clean_text)
                        return CompetitorAnalysis(**data)
                    except Exception as e:
                        # Log the raw text only if it exists
                        raw_text = (
                            response.text
                            if response and hasattr(response, "text")
                            else "None"
                        )
                        print(
                            f"⚠️ Warning: Model returned None & JSON parsing failed. Error: {e}"
                        )
                        print(f"RAW RESPONSE: {raw_text}")
                        # Return a fallback object so monitor.py doesn't crash
                        return CompetitorAnalysis(
                            name="Unknown (Analysis Failed)",
                            value_proposition="Could not extract data.",
                            solutions="N/A",
                            industries="N/A",
                            has_changes=False,
                        )
            else:
                # Return the standard text string
                return response.text


async def execute_tool(session, fn, headless):
    """Helper to run the tool logic safely."""
    try:
        tool_args = dict(fn.args)
        if "url" in tool_args and isinstance(tool_args["url"], str):
            if not tool_args["url"].startswith(("http://", "https://")):
                tool_args["url"] = f"https://{tool_args['url']}"

        # FIX: Added actual tool execution logic
        result = await session.call_tool(fn.name, tool_args)
        return result.content[0].text
    except Exception as e:
        print(f"❌ Tool Execution Error ({fn.name}): {e}")
        return f"Error: {str(e)}"

import streamlit as st
import asyncio
import os
from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.sse import sse_client

# 🔴 TODO: PASTE  MARKETING BACKEND URL HERE
# (Make sure it ends with /sse)
MCP_SERVER_URL = "https://marketing-mcp-4v4sc3n5qq-uc.a.run.app/sse"

PROJECT_ID = os.popen("gcloud config get-value project").read().strip()
LOCATION = "us-central1"

st.set_page_config(page_title="Marketing Analyst AI", page_icon="🕵️‍♀️", layout="wide")

# --- PASSWORD PROTECTION ---
def check_password():
    """Returns `True` if the user had the correct password."""
    
    # 1. Check if password is in secrets (Local dev) or env vars (Cloud Run)
    # We look for "password" in Streamlit secrets
    if "password" not in st.secrets:
        st.error("❌ No password set in secrets.toml!")
        return False

    stored_password = st.secrets["password"]

    # 2. Compare with user input
    def password_entered():
        if st.session_state["password"] == stored_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # clear input field
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input(
        "Please enter the access password", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    return False

if not check_password():
    st.stop()  # Stop execution if password is wrong
# ---------------------------

st.title("🕵️‍♀️ Marketing Analyst Agent")
st.markdown("""
**I read websites so you don't have to.** Give me a URL, and I will analyze the value proposition, target audience, and competitive positioning.
""")

# Initialize Chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

async def run_agent_turn(user_prompt):
    """Connects to the backend and runs the agent."""
    # We add timeout=300 (5 minutes) to prevent disconnection during long tasks
    async with sse_client(MCP_SERVER_URL, timeout=300) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            
            # Get Tools
            tools_list = await session.list_tools()
            gemini_tools = [{"name": t.name, "description": t.description, "parameters": t.inputSchema} for t in tools_list.tools]

            # Setup Gemini
            client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
            chat = client.chats.create(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(
                    system_instruction="""
                    You are a Senior Marketing Strategist.
                    YOUR CAPABILITIES:
                    1. You can visit any URL using the 'analyze_website' tool.
                    2. You extract key insights: Value Prop, Target Audience, Tone of Voice.
                    RULES:
                    - ALWAYS usage 'analyze_website' when the user provides a URL.
                    - Do NOT hallucinate content. If the tool fails, say so.
                    - Format your output with clear headers (##) and bullet points.
                    """,
                    tools=[types.Tool(function_declarations=gemini_tools)]
                )
            )

            # Send User Message
            response = chat.send_message(user_prompt)

            # Handle Tool Calls (Loop until model stops calling tools)
            while True:
                # 1. Identify all function calls in the current response
                # Gemini might send text + tool calls, or multiple tool calls
                call_parts = [p for p in response.candidates[0].content.parts if p.function_call]
                
                # If no function calls, we are done with the loop
                if not call_parts:
                    break 

                # 2. Execute ALL tools in this turn
                function_responses = []
                
                # Create a status container to show progress
                with st.status(f"🕵️‍♀️ Agent is working...", expanded=True) as status:
                    
                    for part in call_parts:
                        fn = part.function_call
                        st.write(f"Executing: {fn.name}")
                        
                        # Call the MCP server
                        try:
                            result = await session.call_tool(fn.name, arguments=fn.args)
                            tool_output = result.content[0].text
                        except Exception as e:
                            tool_output = f"Error executing tool: {str(e)}"

                        # Add to the batch of responses
                        function_responses.append(
                            types.Part.from_function_response(
                                name=fn.name, 
                                response={"result": tool_output}
                            )
                        )
                    
                    status.update(label="✅ Tools Completed", state="complete", expanded=False)

                # 3. Send ALL results back to Gemini at once
                # This fixes the "400" error by ensuring request/response counts match
                response = chat.send_message(function_responses)

            return response.text

# Chat Input
if prompt := st.chat_input("Check out pulsarplatform.com"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if "REPLACE_ME" in MCP_SERVER_URL:
            st.error("❌ You forgot to update the MCP_SERVER_URL in app.py!")
        else:
            response_text = asyncio.run(run_agent_turn(prompt))
            st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
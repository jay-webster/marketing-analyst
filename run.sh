#!/bin/bash

# 1. Start the Jina/MCP Server in the background
echo "🚀 Starting MCP Server..."
python server.py &
SERVER_PID=$!

# 2. Wait 5 seconds for the server to wake up
sleep 5

# 3. Run the Daily Brief Logic
echo "🚀 Starting Daily Brief Monitor..."
python monitor.py

# 4. Cleanup: When monitor finishes, stop the server
kill $SERVER_PID
echo "✅ Job Complete."

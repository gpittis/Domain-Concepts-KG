"""
Simple test script for /llms/claude_tools endpoint
Loads API credentials from environment variables
"""

import asyncio
import requests
import json
import os
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# Load environment variables
load_dotenv()

API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
MCP_SERVER_PATH = os.getenv("MCP_SERVER_PATH", "./mcp_server.py")


async def get_mcp_tools(server_path: str) -> tuple:
    """Connect to MCP server and get available tools."""
    print(f"🔌 Connecting to MCP server: {server_path}")
    
    server_params = StdioServerParameters(
        command="python",
        args=[server_path]
    )
    
    server_context = stdio_client(server_params)
    read, write = await server_context.__aenter__()
    
    mcp_client = ClientSession(read, write)
    await mcp_client.__aenter__()
    await mcp_client.initialize()
    
    response = await mcp_client.list_tools()
    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        }
        for tool in response.tools
    ]
    
    print(f"✅ Found {len(tools)} tools")
    for tool in tools:
        print(f"   • {tool['name']}")
    print()
    
    return mcp_client, server_context, tools


def call_claude_api(messages: list, tools: list, max_tokens: int = 8000) -> dict:
    """Call the /llms/claude_tools endpoint"""
    payload = {
        "messages": {"messages": messages},
        "tools": tools,
        "max_tokens": max_tokens,
        "model_id": "claude-sonnet-4@20250514"
    }
    
    headers = {
        "Content-Type": "application/json",
        "access_token": API_KEY
    }
    
    response = requests.post(
        f"{API_URL}/llms/claude_tools",
        json=payload,
        headers=headers,
        timeout=60
    )
    if not response.ok:
        print("Status:", response.status_code)
        print("Resp headers:", dict(response.headers))
        print("Resp text:", response.text[:4000])
        response.raise_for_status()
    return response.json()


async def execute_tool(mcp_client, tool_name: str, tool_input: dict) -> str:
    """Execute a tool via MCP"""
    result = await mcp_client.call_tool(tool_name, tool_input)
    
    if hasattr(result, 'content'):
        if isinstance(result.content, list):
            return json.dumps([
                c.model_dump() if hasattr(c, 'model_dump') else c 
                for c in result.content
            ])
        return json.dumps(result.content)
    return json.dumps(str(result))


async def main():
    """Main function"""
    if not API_URL or not API_KEY:
        print("❌ Error: API_URL and API_KEY must be set in .env file")
        return
    
    print(f"🚀 Using API: {API_URL}\n")
    
    # Get tools from MCP server
    mcp_client, server_context, tools = await get_mcp_tools(MCP_SERVER_PATH)
    
    try:
        # User query
        # "Find 15 functional requirements for robotic navigation domain."
        # "Find 15 functional requirements for SLAM (Simultaneous Localization and Mapping) domain."
        # "Find 15 functional requirements for ROS (Robot Operating System) domain."
        # "Find 15 functional requirements for ROS (Robot Operating System) as middleware."
        # "Find 15 functional requirements for cryptocurrency trading domain."
        # "Find 15 functional requirements for crypto-currency trading domain."
        # "Find 15 functional requirements for crypto trading bot domain."
        # 
        user_query = "Find 15 functional requirements for computer vision domain."
        print(f"💬 Query: {user_query}\n")
        
        messages = [
        {
            "role": "user",
            "content":
            "If you want to use more than one tool, then Do it and dont ask for permission."
            "You have exactly ONE tool-use round."
        },
        {"role": "user", "content": user_query},
        {"role": "user", 
         "content": 
         "Your goal is to identify Functional Requirements (FRs) for the domain mentioned in the user prompt (only if a domain is present). "
         "If the domain name is complex (e.g., Robot Operating System), split it into its component words (e.g., robot, operating, system), and run the necessary tools using both: "
         "(a) the abbreviation of the domain (e.g., ros), and "
         "(b) each component word (e.g., robot, operating, system) as a separate argument. "
         "You MUST steme every word in domain's name. (i.e. nltk Snowball stemmer) and run additionally the necessary tools."
         "All tool arguments MUST be lowercase. "
         "For every Functional Requirement produced, clearly mention the concepts and relationships from which it was derived. "
         "The FRs MUST belong ONLY to the provided domain, and MUST NOT include implementation-level or design-level requirements. "
         "At the end of your response, list all tools used along with the exact arguments passed to each."}]

        # Call Claude
        result = call_claude_api(messages, tools)
        
        # Handle response
        if result.get("stop_reason") == "tool_use":
            print("🔧 Claude wants to use tools:\n")
            
            messages.append({"role": "assistant", "content": result["content"]})
            
            # Execute tools
            tool_results = []
            for block in result["content"]:
                if block["type"] == "tool_use":
                    print(f"  • {block['name']}: {block['input']}")
                    output = await execute_tool(mcp_client, block["name"], block["input"])
                    print(f"    Result: {output}\n")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": output
                    })
            
            # Get final response
            messages.append({"role": "user", "content": tool_results})
            result = call_claude_api(messages, tools)
        
        # Print final answer
        print("✅ Final Response:")
        for block in result["content"]:
            if block["type"] == "text":
                print(block["text"])
    
    finally:
        await mcp_client.__aexit__(None, None, None)
        await server_context.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
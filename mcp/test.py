"""
Simple test script for /llms/claude_tools endpoint
Loads API credentials from environment variables
The test.py file is the MCP client
"""

import asyncio
import requests
import json
import os
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# Load environment variables from .env (API token, API base URL, MCP server path)
load_dotenv()

# Ariadne API credentials / configuration
API_TOKEN = os.getenv("API_KEY") # All API requests require a Bearer token in the Authorization header
BASE_URL = os.getenv("API_URL")

# MCP server path
MCP_SERVER_PATH = os.getenv("MCP_SERVER_PATH")

# provider/model are required fields.
PROVIDER = "gcp"
MODEL = "claude-sonnet-4"


def ariadne_chat(message: str, tools: list, max_tokens: int = 1200) -> dict:
    """
    (single-turn message)
    The endpoint (POST .../api/v1/chat) sends a single message and get the complete response.

    Sends one user prompt plus optional tools.
    Response includes:
      - content: {"type": "text", "text": "The response text"}
      - stop_reason: "end_turn" | "tool_use" | "max_tokens"
      - provider, model and billing information

    When stop_reason == "tool_use", the model wants to call a function.
    """
    r = requests.post(
        f"{BASE_URL}/v1/chat",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json={
            "provider": PROVIDER,
            "model": MODEL,
            "message": message, # the user prompt here
            "tools": tools, # MCP tools array for function calling
            "system": "You are a careful assistant. Follow the user's instructions exactly.", # It is an optional System message, enables prompt caching for Claude models when >1024 tokens. Use it to save tokens for repeated text.
            "max_tokens": max_tokens, # max output tokens (default: 4096)
        },
        timeout=60,
    )
    if not r.ok:
        print("Ariadne /v1/chat failed:", r.status_code)
        print(r.text[:4000])
        r.raise_for_status()
    return r.json() # return the response JSON.


def ariadne_messages(messages: list, tools: list, max_tokens: int = 1800) -> dict:
    """
    (multi-turn messages)
    The endpoint (POST .../api/v1/messages) sends full conversation history with multiple messages. 
    It is the best option for multi-turn conversations with context.

    Used to continue the conversation with AI Agent after "tool_use":
    You send the full conversation history, including:
      - original user prompt
      - assistant content that contains tool_use blocks
      - tool_result blocks with outputs from executed tools

    The model then uses those tool results to produce the final response text.
    """
    r = requests.post(
        f"{BASE_URL}/v1/messages",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json={
            "messages": messages, # an array of messages that contains the full conversation history.
            "provider": PROVIDER,
            "model": MODEL,
            "tools": tools, # MCP tools array
            "max_tokens": max_tokens, # max output tokens (default: 4096)
        },
        timeout=60,
    )
    # print("ARIANDE_MESSAGES TOOLS HERE : \n\n")
    # print(messages[:8000])
    if not r.ok:
        print("Ariadne /v1/messages failed:", r.status_code)
        print(r.text[:4000])
        r.raise_for_status()
    return r.json() # return the response JSON.


def mcp_result_to_tool_result_content(mcp_result) -> str:
    """
    Normalize an MCP tool execution result into a JSON-encoded string.
    """
    if hasattr(mcp_result, "content"):
        try:
            return json.dumps(
                [c.model_dump() if hasattr(c, "model_dump") else c for c in mcp_result.content],
                ensure_ascii=False,
            )
        except Exception:
            return json.dumps(str(mcp_result.content), ensure_ascii=False)
    return json.dumps(str(mcp_result), ensure_ascii=False)


async def main():
    """
    Orchestrates the full tool-calling process:
      - Start MCP server over stdio
      - Discover tools via MCP list_tools()
      - Call Ariadne /chat with tools
      - If tool_use requested:
          - execute tools via MCP call_tool()
          - send tool_result blocks back via Ariadne /messages
      - Print final model response text
    """

    # Fail if API token is missing.
    if not API_TOKEN:
        raise RuntimeError("Missing ARIADNE_API_TOKEN in .env")
    
    """
    ClientSession is the client-side MCP session handler.
    It uses the read/write streams to speak the MCP protocol and provides:
    With ClientSession, you can: 
    1. connect to the MCP server (a handshake) : initialize() 
    2. see all tools of MCP server : list_tools()
    3. use a specific tool of MCP server : call_tool()
    In short: ClientSession is the way to talk to and send commands to the MCP server.
    """

    """
    (Transport Layer)
    stdio_client launches the MCP server as a subprocess and connects via stdin/stdout pipes.
    The stdio_client opens the communication channel between MCP client and MCP server.
    1. sends the MCP client's commands to the MCP server's stdin (i.e. to the input of the server).
    2. reads the MCP server's responses from the MCP server's stdout (i.e. the output of the server) and sends them back to MCP client.
    In short : stdio_client allows the client and server to communicate by writing and reading messages through stdin/stdout.
    """

    # Connect to MCP Server
    server_params = StdioServerParameters(command="python", args=[MCP_SERVER_PATH])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            # MCP initialization handshake.
            await mcp_client.initialize()

            # Get the MCP sever's tools
            resp = await mcp_client.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,  # IMPORTANT for Ariadne API
                }
                for t in resp.tools
            ]

            # Print the tool's name
            print(f"✅ Loaded {len(tools)} MCP tools:")
            for t in tools:
                print(f" - {t['name']}")
                # print(f" - {t['description']}") ############
                # print(f" - {t['inputSchema']}") ###########
                # print() ####################
            print()

            # User prompt: asks the model to produce requirements and optionally use tools.
            user_prompt = (
                "Give me 15 functional requirements for the Deep Learning domain, "
                "so that, based on these, I will create the syntax of a domain specific language to enable citized developers to easily configure and setup DL pipelines, " \
                "without deep technical knowledge of the domain."
                "If you want to use more than one tool, then Do it and dont ask for permission."
                "You have exactly ONE tool-use round."
                "Your goal is to identify Functional Requirements (FRs) for a Domain-Specific Language (DSL) for the Deep Learning domain. "
                "The FRs must focus on dataset definition, multi-stage training workflows, "
                "transfer learning (pretrained/checkpoint initialization, freeze/unfreeze, head replacement), and retraining triggers/strategies (new data, metric drop, drift). "
                "**The FRs MUST belong ONLY to the provided domain and NOT to other relative domains.**"
                "If the domain name is complex (e.g., Robot Operating System), split it into its component words (e.g., robot, operating, system), and run the necessary tools using both: "
                "(a) the abbreviation of the domain (e.g., ros), and "
                "(b) each component word (e.g., robot, operating, system) as a separate argument. "
                "(c) You MUST steme every word in domain's name. (i.e. nltk Snowball stemmer) and run additionally the necessary tools."
                "All tool arguments MUST be lowercase. "
                "For every Functional Requirement produced, clearly mention ALL the relationships from which it was derived. "
                "Assume the user has basic familiarity with the domain, but no deep technical knowledge."
                "Each FR MUST be phrased as a capability of the DSL (e.g., 'The grammar should support : ') and targets what the DSL must express, parameterize, or validate, NOT how it is implemented. "
                "Do NOT reference any algorithms, libraries, or framework implementations in the FRs ensuring that the DSL remains usable by non-experts. "
                "I DONT want the words algorithms,libraries,frameworks."
                "At the end of your response, list all tools used along with the exact arguments passed to each."
            )

            # First call: /chat. The model may respond with stop_reason == "tool_use".
            first = ariadne_chat(user_prompt, tools=tools)

            # If the model didn't request tool use, just print any returned text blocks and exit.
            if first.get("stop_reason") != "tool_use":
                for b in first.get("content", []):
                    if b.get("type") == "text":
                        print(b["text"])
                return
            
            # Here, iam saving the respone content 
            content = first.get("content", [])

            # When stop_reason == "tool_use", the response content includes tool_use blocks.
            # Deduplicate by tool_use id to avoid executing the same tool request twice.
            tool_calls = []
            seen_ids = set()
            for item in content:
                if item.get("type") == "tool_use" and item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    tool_calls.append(item)

            # Print the requested tools with the corresponding input parameters
            print("🔧 Tools requested by Ariadne (will execute):")
            for tc in tool_calls:
                print(f" - {tc['name']} input={tc['input']}")
            print()

            # Execute tools (1 tool_result per tool_use_id)
            # Execute each requested tool via MCP and create the corresponding tool_result blocks.
            # IMPORTANT: tool_result.tool_use_id must match the tool_use.id from the assistant content.
            tool_results = []
            for tc in tool_calls:
                mcp_res = await mcp_client.call_tool(tc["name"], tc["input"])
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": mcp_result_to_tool_result_content(mcp_res),
                    }
                )

            # print("Tools Results : \n\n")
            # for i in range(len(tool_results)):
            #     print(tool_results[i]["content"][:1000])
            # print("\n\n")

            # Build assistant content for the /messages call:
            # keep any assistant text blocks + tool_use blocks (unique ids).
            assistant_content = []
            tool_use_ids = set()
            for item in content:
                if item.get("type") == "text":
                    assistant_content.append(item)
                elif item.get("type") == "tool_use" and item["id"] not in tool_use_ids:
                    tool_use_ids.add(item["id"])
                    assistant_content.append(item)
                    
            # Full conversation history as required by /messages continuation:
            #   1) user prompt
            #   2) assistant tool_use request(s)
            #   3) user tool_result(s) (outputs after executing tools)
            messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_content},
                {"role": "user", "content": tool_results},
            ]

            # Second call: /messages. Model uses tool results to generate final answer.
            final = ariadne_messages(messages, tools=tools)
            # print("FINAL HERE : \n\n")
            # print(final)

            # Print final response.
            for b in final.get("content", []):
                if b.get("type") == "text":
                    print(b["text"])


if __name__ == "__main__":
    asyncio.run(main())

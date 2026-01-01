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

# ✅ Ariadne env vars (όπως τα examples)
API_TOKEN = os.getenv("API_KEY")
BASE_URL = os.getenv("API_URL")

# MCP server
MCP_SERVER_PATH = os.getenv("MCP_SERVER_PATH")

PROVIDER = "gcp"
MODEL = "claude-sonnet-4"


def ariadne_chat(message: str, tools: list, max_tokens: int = 1200) -> dict:
    r = requests.post(
        f"{BASE_URL}/v1/chat",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json={
            "provider": PROVIDER,
            "model": MODEL,
            "message": message,
            "tools": tools,
            "system": "You are a careful assistant. Follow the user's instructions exactly.",
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    if not r.ok:
        print("Ariadne /v1/chat failed:", r.status_code)
        print(r.text[:4000])
        r.raise_for_status()
    return r.json()


def ariadne_messages(messages: list, tools: list, max_tokens: int = 1800) -> dict:
    r = requests.post(
        f"{BASE_URL}/v1/messages",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json={
            "messages": messages,
            "provider": PROVIDER,
            "model": MODEL,
            "tools": tools,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    # print("ARIANDE_MESSAGES TOOLS HERE : \n\n")
    # print(messages[:8000])
    if not r.ok:
        print("Ariadne /v1/messages failed:", r.status_code)
        print(r.text[:4000])
        r.raise_for_status()
    return r.json()


def mcp_result_to_tool_result_content(mcp_result) -> str:
    # safe: JSON string
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
    if not API_TOKEN:
        raise RuntimeError("Missing ARIADNE_API_TOKEN in .env")

    server_params = StdioServerParameters(command="python", args=[MCP_SERVER_PATH])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            await mcp_client.initialize()

            # ✅ Tools from MCP (Ariadne wants inputSchema)
            resp = await mcp_client.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,  # IMPORTANT
                }
                for t in resp.tools
            ]

            print(f"✅ Loaded {len(tools)} MCP tools:")
            for t in tools:
                print(f" - {t['name']}")
                # print(f" - {t['description']}") ############
                # print(f" - {t['inputSchema']}") ###########
                # print() ####################
            print()

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

            first = ariadne_chat(user_prompt, tools=tools)

            if first.get("stop_reason") != "tool_use":
                for b in first.get("content", []):
                    if b.get("type") == "text":
                        print(b["text"])
                return

            content = first.get("content", [])

            # ✅ ABSOLUTELY NECESSARY: dedup tool_use by id (όπως στο ariadne example)
            tool_calls = []
            seen_ids = set()
            for item in content:
                if item.get("type") == "tool_use" and item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    tool_calls.append(item)

            print("🔧 Tools requested by Ariadne (will execute):")
            for tc in tool_calls:
                print(f" - {tc['name']} input={tc['input']}")
            print()

            # Execute tools (1 tool_result per tool_use_id)
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

            # ✅ assistant_content must also have UNIQUE tool_use ids (όπως στο example)
            assistant_content = []
            tool_use_ids = set()
            for item in content:
                if item.get("type") == "text":
                    assistant_content.append(item)
                elif item.get("type") == "tool_use" and item["id"] not in tool_use_ids:
                    tool_use_ids.add(item["id"])
                    assistant_content.append(item)

            messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_content},
                {"role": "user", "content": tool_results},
            ]

            final = ariadne_messages(messages, tools=tools)
            # print("FINAL HERE : \n\n")
            # print(final)
            for b in final.get("content", []):
                if b.get("type") == "text":
                    print(b["text"])


if __name__ == "__main__":
    asyncio.run(main())

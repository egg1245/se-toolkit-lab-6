#!/usr/bin/env python3
"""
Agent CLI with agentic loop and tools.

The agent answers questions by:
1. Calling the LLM with tool definitions
2. If LLM requests a tool, executing it and feeding the result back
3. Repeating until LLM provides a final answer

Usage:
    uv run agent.py "How do you resolve a merge conflict?"

Output:
    {
      "answer": "...",
      "source": "wiki/git-workflow.md#section",
      "tool_calls": [...]
    }
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


def load_config() -> dict[str, str]:
    """Load LLM configuration from environment variables."""
    # Load from .env.agent.secret if it exists
    load_dotenv(".env.agent.secret")
    # Also load .env.docker.secret for LMS_API_KEY
    load_dotenv(".env.docker.secret")

    config = {
        "api_key": os.getenv("LLM_API_KEY"),
        "api_base": os.getenv("LLM_API_BASE"),
        "model": os.getenv("LLM_MODEL"),
    }

    # Validate required config
    missing = [k for k, v in config.items() if not v]
    if missing:
        raise ValueError(
            f"Missing LLM configuration: {', '.join(missing)}. "
            f"Please set LLM_API_KEY, LLM_API_BASE, and LLM_MODEL in .env.agent.secret or environment."
        )

    return config


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return the tool schemas for function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from the project repository to find answers to questions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git.md' or 'backend/app/main.py')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at a given path to discover available documentation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path from project root (e.g., 'wiki' or 'backend/app/routers')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Query the backend API to get runtime data about items, interactions, analytics, and system status",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, etc.)",
                        },
                        "path": {
                            "type": "string",
                            "description": "API endpoint path (e.g., '/items/' or '/analytics/completion-rate')",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body for POST/PUT requests",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


def validate_path(path_str: str) -> Path:
    """Validate that a path doesn't escape the project root."""
    project_root = Path(__file__).parent.resolve()
    target_path = (project_root / path_str).resolve()

    # Ensure target is within project root
    try:
        target_path.relative_to(project_root)
    except ValueError:
        raise ValueError(f"Path traversal not allowed: {path_str}")

    return target_path


def read_file(path_str: str) -> str:
    """Read a file from the project."""
    try:
        target_path = validate_path(path_str)

        if not target_path.exists():
            return f"Error: File not found: {path_str}"

        if not target_path.is_file():
            return f"Error: Not a file: {path_str}"

        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Limit content size to avoid overwhelming the LLM
        max_size = 50000
        if len(content) > max_size:
            content = content[:max_size] + f"\n\n... (file truncated, original size: {len(content)} bytes)"

        return content
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path_str: str) -> str:
    """List files and directories at a given path."""
    try:
        target_path = validate_path(path_str)

        if not target_path.exists():
            return f"Error: Directory not found: {path_str}"

        if not target_path.is_dir():
            return f"Error: Not a directory: {path_str}"

        entries = sorted([entry.name for entry in target_path.iterdir()])
        return "\n".join(entries)
    except Exception as e:
        return f"Error listing files: {e}"


def query_api(method: str, path: str, body: str = "") -> str:
    """Query the backend API."""
    try:
        # Get configuration from environment
        api_key = os.getenv("LMS_API_KEY")
        if not api_key:
            return "Error: LMS_API_KEY not set in environment"

        base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")
        url = f"{base_url}{path}"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Make the API request
        if method.upper() == "GET":
            response = httpx.get(url, headers=headers, timeout=10.0)
        elif method.upper() == "POST":
            response = httpx.post(url, headers=headers, content=body, timeout=10.0)
        elif method.upper() == "PUT":
            response = httpx.put(url, headers=headers, content=body, timeout=10.0)
        elif method.upper() == "DELETE":
            response = httpx.delete(url, headers=headers, timeout=10.0)
        else:
            return f"Error: Unsupported HTTP method: {method}"

        # Return response as JSON
        return json.dumps(
            {
                "status_code": response.status_code,
                "body": response.text,
            }
        )
    except httpx.TimeoutException:
        return json.dumps(
            {
                "status_code": 0,
                "body": "Error: API request timed out",
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "status_code": 0,
                "body": f"Error: {str(e)}",
            }
        )


def execute_tool(tool_name: str, tool_args: dict[str, Any]) -> str:
    """Execute a tool and return its result."""
    if tool_name == "read_file":
        return read_file(tool_args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(tool_args.get("path", ""))
    elif tool_name == "query_api":
        return query_api(
            tool_args.get("method", "GET"),
            tool_args.get("path", ""),
            tool_args.get("body", ""),
        )
    else:
        return f"Error: Unknown tool: {tool_name}"


def call_llm_with_tools(
    messages: list[dict[str, Any]], config: dict[str, str]
) -> dict[str, Any]:
    """Call the LLM with tool definitions and return the response."""
    url = f"{config['api_base']}/chat/completions"

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config["model"],
        "messages": messages,
        "tools": get_tool_schemas(),
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=60.0)
        response.raise_for_status()

        result = response.json()
        if "choices" not in result or len(result["choices"]) == 0:
            raise ValueError(f"Unexpected LLM response format: {result}")

        message = result["choices"][0]["message"]
        # Include finish_reason in response for better handling
        finish_reason = result["choices"][0].get("finish_reason")
        if finish_reason:
            message["finish_reason"] = finish_reason
        return message

    except httpx.HTTPError as e:
        print(f"HTTP error calling LLM: {e}", file=sys.stderr)
        raise
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"Error parsing LLM response: {e}", file=sys.stderr)
        raise


def run_agent_loop(
    question: str, config: dict[str, str], max_iterations: int = 10
) -> dict[str, Any]:
    """Run the agentic loop until the LLM provides a final answer."""
    system_prompt = """You are a helpful assistant that answers questions about a software project by reading documentation and querying its backend API.

You have access to three tools:

1. **read_file(path)** - Read documentation and source code files from the project
2. **list_files(path)** - Discover what files and directories are available
3. **query_api(method, path, body)** - Query the backend API for runtime data

INSTRUCTIONS:

1. Always use tools to find answers - never guess or rely on pre-training
2. For each question, explore systematically: list_files → read_file or query_api → analyze
3. Continue using tools until you have enough information for a complete answer
4. Only stop when you have found the actual data/files/code answering the question

WORKFLOW BY QUESTION TYPE:

- **Wiki/Documentation questions**: list_files('wiki') → read_file('wiki/*.md')
- **Code/Architecture questions**: list_files('backend') → read_file specific files
- **API/Data questions**: query_api('GET', '/learners/', {}) or appropriate endpoint

CRITICAL REQUIREMENTS FOR FINAL ANSWER:

- MUST include exact sources (file paths or API endpoints)
- MUST only answer based on what you found in tools, never assumptions
- MUST continue searching if initial results are incomplete
- For data/learner questions: ALWAYS use query_api, do NOT stop early
- ALWAYS fully explore directories before giving up

REMEMBER: 
- Keep searching until you find the actual answer
- If initial tool use doesn't work, try alternatives
- Never output incomplete answers - if you don't have full info yet, keep exploring"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    tool_calls_log = []

    for iteration in range(max_iterations):
        print(f"Iteration {iteration + 1}/{max_iterations}", file=sys.stderr)

        # Call LLM
        response = call_llm_with_tools(messages, config)

        # Add assistant message to history
        # For Qwen Code API compatibility, include tool_calls if present
        assistant_msg = {
            "role": "assistant",
            "content": response.get("content") or "",
        }
        if "tool_calls" in response and response["tool_calls"]:
            assistant_msg["tool_calls"] = response["tool_calls"]
        messages.append(assistant_msg)

        # Check for tool calls
        if "tool_calls" not in response or not response["tool_calls"]:
            # No tool calls - check if this is really the final answer
            content = response.get("content") or ""
            
            # If content looks incomplete, keep exploring
            # Consider it incomplete if:
            # - Ends with incomplete code block
            # - Very short placeholder text (< 150 chars) that looks like thinking/setup
            is_incomplete = (
                content.strip().endswith("```") or  # Incomplete code block
                (len(content.strip()) < 150 and (
                    content.strip().startswith("Let me ") or
                    content.strip().startswith("I need to") or
                    content.strip().startswith("I'll") or
                    content.strip().startswith("Let me check")
                ))
            )
            
            if is_incomplete:
                # This is an incomplete intermediate response, force LLM to continue
                messages.append({
                    "role": "user",
                    "content": "Continue exploring. Use tools to find the complete information needed to answer the question fully."
                })
                continue
            
            # This is the final answer
            source = ""

            # Try to extract source from answer
            if "wiki/" in content or "backend/" in content:
                # Simple heuristic: look for file paths
                import re

                matches = re.findall(r"([a-zA-Z0-9_\-./]+\.(md|py|yaml|json|sql|txt))", content)
                if matches:
                    source = matches[0][0]  # Use first found path

            return {
                "answer": content,
                "source": source,
                "tool_calls": tool_calls_log,
            }

        # Execute tool calls
        for tool_call in response["tool_calls"]:
            tool_name = tool_call.get("function", {}).get("name")
            tool_args_str = tool_call.get("function", {}).get("arguments", "{}")

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            print(f"  Executing tool: {tool_name}({tool_args})", file=sys.stderr)

            tool_result = execute_tool(tool_name, tool_args)

            # Log tool call
            tool_calls_log.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": tool_result,
                }
            )

            # Add tool result to message history
            tool_call_id = tool_call.get("id", f"tool_{len(tool_calls_log)}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result,
                }
            )

    # Max iterations exceeded
    return {
        "answer": "Error: Agent reached maximum iterations without finding a final answer.",
        "source": "",
        "tool_calls": tool_calls_log,
    }


def main() -> int:
    """Main entry point for the agent CLI."""
    parser = argparse.ArgumentParser(description="Agent that answers questions using an LLM and tools")
    parser.add_argument("question", help="The question to ask the agent")

    args = parser.parse_args()

    try:
        # Load LLM configuration
        config = load_config()

        # Run agent loop
        result = run_agent_loop(args.question, config)

        # Output JSON to stdout
        print(json.dumps(result))
        return 0

    except Exception as e:
        print(f"Agent error: {e}", file=sys.stderr)
        error_response = {
            "answer": f"Error: {str(e)}",
            "source": "",
            "tool_calls": [],
        }
        print(json.dumps(error_response))
        return 1


if __name__ == "__main__":
    sys.exit(main())

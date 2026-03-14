# Task 1: Call an LLM from Code - Implementation Plan

## Overview

Build a basic CLI agent (`agent.py`) that:

1. Takes a user question as a command-line argument
2. Sends it to an LLM provider
3. Returns structured JSON output with the answer

## LLM Provider Choice

### Qwen Code API on VM (qwen3-coder-plus)

Rationale:

- Free and locally hosted on personal VM
- Strong tool-calling support (OpenAI-compatible)
- No rate limits, no credit card required
- Privacy preserved (LLM stays on your machine)
- Accessible remotely from laptop via SSH tunnel
- 1000 free requests per day

Setup:
1. VM: Install Qwen Code in `~/qwen-code-oai-proxy/`
2. VM: Set `QWEN_API_KEY` in `.env`
3. Laptop: Set `LLM_API_KEY=<same-key>`, `LLM_API_BASE=http://<vm-ip>:5000/v1`

Configuration:

- `LLM_API_KEY`: Qwen Code API key (from VM, same as QWEN_API_KEY)
- `LLM_API_BASE`: `http://<vm-ip>:5000/v1`
- `LLM_MODEL`: `qwen3-coder-plus`

## Agent Architecture

### Input

- Command line argument: question string
- Environment variables: LLM_API_KEY, LLM_API_BASE, LLM_MODEL

### Processing

1. Load LLM config from environment variables (.env.agent.secret)
2. Create a chat message with the user's question
3. Call LLM API using OpenAI-compatible chat completions endpoint
4. Parse the response

### Output

Single JSON line to stdout:

```json
{
  "answer": "The answer text",
  "tool_calls": []
}
```

### Error Handling

- Validate environment variables are set
- Handle network/API errors gracefully
- Ensure exit code 0 on success
- All debug output goes to stderr

## Implementation Details

### Dependencies

- `httpx`: HTTP client for async API calls (already in pyproject.toml)
- `python-dotenv`: Load environment variables
- Standard library: argparse, json, sys

### File Structure

- `agent.py`: Main CLI entry point
- `.env.agent.secret`: Environment configuration (not committed)
- Tests: test_agent.py with at least 1 regression test

### Code Structure for agent.py

1. Parse CLI arguments (question)
2. Load environment variables
3. Initialize LLM client
4. Send request to LLM
5. Format response as JSON
6. Output to stdout

## Testing Strategy

- Unit test: Call agent.py as subprocess with a simple question
- Verify JSON output structure has `answer` and `tool_calls` fields
- Verify exit code is 0
- Verify all output is valid JSON (no debug output mixed in)

## Potential Issues & Solutions

- **Rate limiting**: OpenRouter free tier has limits, but should be fine for initial development
- **API key missing**: Validate at startup, provide clear error message
- **Malformed response**: Handle cases where LLM returns unexpected format
- **Timeout**: Set reasonable timeout (60 seconds per requirement)

## Next Steps

After Task 1 completion:

- Task 2: Add tools (read_file, list_files) and implement agentic loop
- Task 3: Add query_api tool to access backend, run benchmark

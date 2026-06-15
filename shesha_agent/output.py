"""Terminal output helpers for the form design agent."""

import json
import textwrap

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

# ANSI colors
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Max characters to show for tool input/output previews
PREVIEW_LEN = 300


def _truncate(text: str, limit: int = PREVIEW_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _format_input(tool_input: dict) -> str:
    """Format tool input as a compact, readable string."""
    try:
        raw = json.dumps(tool_input, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        raw = str(tool_input)
    return _truncate(raw)


def _format_result(content) -> str:
    """Extract readable text from a ToolResultBlock's content."""
    if content is None:
        return "(no output)"
    if isinstance(content, str):
        return _truncate(content)
    if isinstance(content, list):
        # list of content blocks — extract text parts
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return _truncate("\n".join(texts)) if texts else _truncate(str(content))
    return _truncate(str(content))


def _indent(text: str, prefix: str = "    ") -> str:
    return textwrap.indent(text, prefix)


async def collect_and_print(client: ClaudeSDKClient) -> str:
    """Drain the response stream, print live, return full text."""
    parts: list[str] = []

    async for msg in client.receive_response():
        if isinstance(msg, SystemMessage):
            agent_type = msg.data.get("agent_type", "")
            if agent_type:
                if "start" in msg.subtype.lower():
                    print(f"\n{YELLOW}{BOLD}[Phase -> {agent_type}]{RESET}")
                elif "stop" in msg.subtype.lower():
                    print(f"{YELLOW}[Phase <- {agent_type} done]{RESET}\n")

        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
                    print(block.text, end="", flush=True)

                elif isinstance(block, ToolUseBlock):
                    short_name = block.name.split("__")[-1]
                    print(f"\n  {CYAN}{BOLD}-> {block.name}{RESET}")
                    print(f"{DIM}{_indent(_format_input(block.input))}{RESET}")

        elif isinstance(msg, UserMessage):
            # Tool results come back as UserMessage with ToolResultBlock content
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        color = RED if block.is_error else GREEN
                        label = "ERROR" if block.is_error else "result"
                        result_text = _format_result(block.content)
                        print(f"  {color}<- {label}:{RESET}")
                        print(f"{DIM}{_indent(result_text)}{RESET}")

        elif isinstance(msg, ResultMessage):
            cost = msg.total_cost_usd or 0.0
            print(
                f"\n{DIM}[turns={msg.num_turns}, "
                f"cost=${cost:.4f}, "
                f"time={msg.duration_ms / 1000:.1f}s]{RESET}"
            )

    return "\n".join(parts)

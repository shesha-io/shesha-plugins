"""SDK configuration builder for the form design agent."""

from claude_agent_sdk import ClaudeAgentOptions

from .agents import ORCHESTRATOR_PROMPT, build_agents

# Tools the orchestrator auto-approves (superset of all subagent tools)
ALLOWED_TOOLS = [
    # Core
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "Skill", "TodoWrite",
    # MCP: shesha-mcp
    "mcp__shesha-mcp__search_entities",
    "mcp__shesha-mcp__search_forms",
    "mcp__shesha-mcp__search_modules",
    "mcp__shesha-mcp__search_reference_lists",
    "mcp__shesha-mcp__create_form_configuration",
    "mcp__shesha-mcp__update_form_configuration",
    "mcp__shesha-mcp__get_form_test_url",
]


def build_options(cwd: str = ".", backend_cmd: str | None = None) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions with subagents, MCP servers, and plugins."""
    return ClaudeAgentOptions(
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": ORCHESTRATOR_PROMPT,
        },
        agents=build_agents(backend_cmd),
        mcp_servers={
            "shesha-mcp": {
                "type": "sse",
                "url": "http://127.0.0.1:8000/sse",
            },
            "playwright": {
                "command": "cmd",
                "args": [
                    "/c", "npx", "-y",
                    "@executeautomation/playwright-mcp-server",
                    "--headless", "false",
                ],
            },
        },
        permission_mode="acceptEdits",
        cwd=cwd,
        plugins=[{"type": "local", "path": "./plugins/shesha-developer"}],
        setting_sources=["user", "project"],
        allowed_tools=ALLOWED_TOOLS,
        max_turns=50,
    )

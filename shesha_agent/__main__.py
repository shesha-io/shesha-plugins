"""CLI entry point for the Shesha form design agent.

Usage:
    py -m shesha_agent "Create a patient registration form"
    py -m shesha_agent "Add CRUD for vehicles" --cwd ../my-project
    py -m shesha_agent "Create a form for orders" --backend-cmd "dotnet run --project src/MyApp.Web"
"""

import asyncio
import shutil
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient

from .options import build_options
from .output import BOLD, DIM, RESET, collect_and_print

# Plugin cache dir — clear on every run so skills always use latest source
_PLUGIN_CACHE = Path.home() / ".claude" / "plugins" / "cache" / "shesha-plugins"


def parse_args() -> tuple[str, str, str | None, str | None]:
    """Parse CLI arguments: request, --cwd, --backend-cmd, --module."""
    args = sys.argv[1:]
    request = ""
    cwd = "."
    backend_cmd = None
    module = None

    i = 0
    while i < len(args):
        if args[i] == "--cwd" and i + 1 < len(args):
            cwd = args[i + 1]
            i += 2
        elif args[i] == "--backend-cmd" and i + 1 < len(args):
            backend_cmd = args[i + 1]
            i += 2
        elif args[i] == "--module" and i + 1 < len(args):
            module = args[i + 1]
            i += 2
        elif not args[i].startswith("--"):
            request = args[i]
            i += 1
        else:
            i += 1

    return request, cwd, backend_cmd, module


async def main():
    request, cwd, backend_cmd, module = parse_args()

    if not request:
        print(
            "Usage: py -m shesha_agent \"<request>\" [--cwd <path>] "
            "[--backend-cmd <cmd>] [--module <name>]"
        )
        sys.exit(1)

    # Clear stale plugin cache so skills always use latest source
    if _PLUGIN_CACHE.exists():
        shutil.rmtree(_PLUGIN_CACHE, ignore_errors=True)

    print(f"{BOLD}Request:{RESET} {request}")
    print(f"{DIM}cwd={cwd}{RESET}")
    if backend_cmd:
        print(f"{DIM}backend-cmd={backend_cmd}{RESET}")
    if module:
        print(f"{DIM}module={module}{RESET}")
    print()

    options = build_options(cwd=cwd, backend_cmd=backend_cmd)

    module_hint = f"\nTarget module: {module}" if module else ""

    async with ClaudeSDKClient(options=options) as client:
        # -- Phase 1: Discovery & Planning --
        await client.query(
            f"{request}{module_hint}\n\n"
            "Start with Phase 1: delegate to the discovery agent to search "
            "the Shesha backend and produce a structured plan."
        )
        await collect_and_print(client)

        # -- Approval checkpoint --
        print(f"\n{BOLD}--- Plan Complete ---{RESET}")
        approval = input("Proceed? (yes / no / adjust: <feedback>) > ").strip()

        if approval.lower() == "no":
            print("Cancelled.")
            return

        if approval.lower().startswith("adjust:"):
            feedback = approval[len("adjust:"):].strip()
            await client.query(
                f"The user wants adjustments to the plan: {feedback}\n\n"
                "Revise the plan by delegating to the discovery agent again, "
                "then present the updated plan."
            )
            await collect_and_print(client)

            print(f"\n{BOLD}--- Revised Plan ---{RESET}")
            confirm = input("Proceed with revised plan? (yes / no) > ").strip()
            if confirm.lower() != "yes":
                print("Cancelled.")
                return

        # -- Phases 2 + 3: Execute --
        await client.query(
            "The plan is approved. Execute it now:\n"
            "1. Check the plan's 'Domain Changes Required' field.\n"
            "   - If YES: delegate to domain-builder with the domain changes list.\n"
            "   - If NO: skip to step 2.\n"
            "2. Delegate to form-builder with the 'Forms to Create' table "
            "and 'Execution Order'.\n"
            "3. If form-builder reports DOMAIN GAPS DETECTED, delegate those gaps "
            "to domain-builder, then re-delegate to form-builder to continue.\n"
            "4. Present a final summary with all form names and test URLs."
        )
        await collect_and_print(client)

        print(f"\n{BOLD}--- Complete ---{RESET}")


asyncio.run(main())

#!/usr/bin/env python3
"""
Natural-language agent CLI.
Allows querying the pipeline state conversationally.

Usage:
    python run_chat.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.prompt  import Prompt

console = Console()


def main():
    from config import get_config
    config = get_config()

    if not config.anthropic_key:
        console.print("[red]ANTHROPIC_API_KEY not set in .env[/red]")
        sys.exit(1)

    from src.nl_agent import NLAgent
    agent   = NLAgent(config)
    history = []

    console.rule("[bold cyan]Weather Pipeline Chat Agent[/bold cyan]")
    console.print("Ask about forecasts, alerts, station health, or run the pipeline.")
    console.print("Type [bold]exit[/bold] or [bold]quit[/bold] to leave.\n")

    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye[/dim]")
            break

        if user_input.strip().lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye[/dim]")
            break

        if not user_input.strip():
            continue

        try:
            response = agent.chat(user_input, history)
            console.print(f"\n[bold cyan]Agent:[/bold cyan] {response}\n")
            history.append({"role": "user",      "content": user_input})
            history.append({"role": "assistant",  "content": response})
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")


if __name__ == "__main__":
    main()

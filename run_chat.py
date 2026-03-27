#!/usr/bin/env python3
"""
Natural-language agent CLI.
Allows querying the pipeline state conversationally.

Usage:
    python run_chat.py                          # generic NL agent
    python run_chat.py --phone +919876543210    # conversational agent with farmer identity
"""

import argparse
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.prompt  import Prompt

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Weather Pipeline Chat Agent")
    parser.add_argument("--phone", type=str, default=None,
                        help="Farmer phone number for personalized conversation")
    args = parser.parse_args()

    from config import get_config
    config = get_config()

    if not config.anthropic_key:
        console.print("[red]ANTHROPIC_API_KEY not set in .env[/red]")
        sys.exit(1)

    history    = []
    session_id = str(uuid.uuid4())

    if args.phone:
        from src.conversation import ConversationalAgent
        agent = ConversationalAgent(config)

        console.rule("[bold cyan]Weather Pipeline Chat — Personalized Mode[/bold cyan]")
        console.print(f"Identifying farmer: {args.phone}...")

        identified = asyncio.run(agent.identify(args.phone))
        if identified:
            p = agent.farmer_profile
            console.print(f"[green]Identified:[/green] {p.aadhaar.name} ({p.aadhaar.name_local})")
            console.print(f"  District: {p.aadhaar.district}, {p.aadhaar.state}")
            console.print(f"  Crops: {', '.join(p.primary_crops)}")
            console.print(f"  Area: {p.total_area:.2f} ha")
            console.print(f"  Language: {p.aadhaar.language}\n")
        else:
            console.print(f"[yellow]No farmer found for {args.phone}. Continuing in generic mode.[/yellow]\n")
    else:
        from src.nl_agent import NLAgent
        agent = NLAgent(config)
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
            response = agent.chat(user_input, history,
                                  session_id=session_id)
            console.print(f"\n[bold cyan]Agent:[/bold cyan] {response}\n")
            history.append({"role": "user",      "content": user_input})
            history.append({"role": "assistant",  "content": response})
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")


if __name__ == "__main__":
    main()

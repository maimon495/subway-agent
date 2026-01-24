#!/usr/bin/env python3
"""Command-line interface for the NYC Subway Agent."""

import sys
from .agent import chat, clear_history


def print_banner():
    """Print the welcome banner."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║              NYC Subway Agent 🚇                          ║
║                                                           ║
║  Ask me about subway routes, train times, and stations!  ║
║                                                           ║
║  Examples:                                                ║
║    - How do I get from Times Square to Brooklyn Bridge?  ║
║    - When is the next 1 train at 72nd St?                ║
║    - What lines stop at Union Square?                    ║
║                                                           ║
║  Commands:                                                ║
║    /clear  - Clear conversation history                  ║
║    /quit   - Exit the program                            ║
╚═══════════════════════════════════════════════════════════╝
""")


def main():
    """Run the CLI chat interface."""
    print_banner()

    user_id = "cli_user"

    while True:
        try:
            # Get user input
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ["/quit", "/exit", "/q"]:
                print("\nGoodbye! Safe travels! 🚇")
                break

            if user_input.lower() == "/clear":
                clear_history(user_id)
                print("\n[Conversation history cleared]")
                continue

            # Get response from agent
            print("\nAgent: ", end="", flush=True)
            response = chat(user_input, user_id)
            print(response)

        except KeyboardInterrupt:
            print("\n\nGoodbye! Safe travels! 🚇")
            break
        except Exception as e:
            print(f"\n[Error: {e}]")
            print("Please try again or type /quit to exit.")


if __name__ == "__main__":
    main()

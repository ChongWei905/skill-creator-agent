from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from skill_creator_agent.data_agent_bridge import (
    DEFAULT_VERIFICATION_CONFIG,
    build_data_agent_session,
    extract_last_message_text,
)
from skill_creator_agent.paths import project_path


def build_parser() -> argparse.ArgumentParser:
    """Build the interactive CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Interactive multi-turn CLI for skill_creator via Ferry DataAgent.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_VERIFICATION_CONFIG),
        help="Base skill_creator config YAML. Uses project config.yaml when present.",
    )
    parser.add_argument(
        "--skills-root",
        default=str(project_path("skills")),
        help="Skill root to expose to the runtime.",
    )
    parser.add_argument(
        "--graph-base-url",
        default="http://127.0.0.1:8000",
        help="Graph API base URL.",
    )
    parser.add_argument(
        "--graph-timeout",
        type=int,
        default=30,
        help="Graph API timeout in seconds.",
    )
    parser.add_argument(
        "--disable-graph",
        action="store_true",
        help="Disable graph tools for this verification session.",
    )
    parser.add_argument(
        "--user-id",
        default="weichong",
        help="User id recorded in Ferry state.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Reuse a fixed session id for multi-turn validation.",
    )
    parser.add_argument(
        "--output-root",
        default=str(project_path(".tmp", "data_agent_multiturn")),
        help="Directory root used for Ferry run outputs.",
    )
    parser.add_argument(
        "--materialized-config",
        default=None,
        help="Optional path for the rendered Ferry YAML config.",
    )
    parser.add_argument(
        "--turn",
        action="append",
        default=[],
        help="Provide one or more turns non-interactively. May be repeated.",
    )
    parser.add_argument(
        "--show-state-json",
        action="store_true",
        help="Print the full final state as JSON after each turn.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the multi-turn skill creator shell."""
    return build_parser().parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    """Run the async CLI entrypoint."""
    args = parse_args(argv)
    session = build_data_agent_session(
        args.config,
        skills_root=args.skills_root,
        graph_enabled=not args.disable_graph,
        graph_base_url=args.graph_base_url,
        graph_timeout=args.graph_timeout,
        user_id=args.user_id,
        session_id=args.session_id,
        output_root=args.output_root,
        materialized_config_path=args.materialized_config,
    )

    print("Skill Creator DataAgent CLI")
    print(f"- ferry config: {session.ferry_config_path}")
    print(f"- session_id:   {session.session_id}")
    print(f"- output_path:  {session.output_path}")
    print(f"- skills_root:  {session.runtime.settings.skills_root}")
    print(f"- graph:        {'enabled' if session.runtime.settings.graph_enabled else 'disabled'}")
    if session.runtime.settings.graph_enabled:
        print(f"- graph_url:    {session.runtime.settings.graph_base_url}")
    print("")

    if args.turn:
        for turn in args.turn:
            await _run_turn(session, turn, show_state_json=args.show_state_json)
        return 0

    print("Commands: /skills, /config, /stage, /reset, /help, /quit")
    while True:
        try:
            user_input = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not user_input:
            continue
        if user_input == "/quit":
            print("Bye.")
            return 0
        if user_input == "/help":
            print("Commands: /skills, /config, /stage, /reset, /help, /quit")
            continue
        if user_input == "/skills":
            print(json.dumps(session.runtime.list_skills(), ensure_ascii=False, indent=2))
            continue
        if user_input == "/config":
            print(session.ferry_config_path)
            continue
        if user_input == "/stage":
            print(
                json.dumps(
                    {
                        "workflow_stage": session.workflow_stage,
                        "active_turn_stage": session.active_turn_stage,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue
        if user_input == "/reset":
            previous = session.session_id
            session.reset()
            print(f"Session reset: {previous} -> {session.session_id}")
            print(f"New output_path: {session.output_path}")
            continue

        await _run_turn(session, user_input, show_state_json=args.show_state_json)


def main() -> int:
    """Run the synchronous CLI entrypoint."""
    return asyncio.run(async_main())


async def _run_turn(session: Any, query: str, *, show_state_json: bool) -> None:
    print(
        f"\n[run_id={session.next_run_id}] sending..."
        f" (workflow_stage={session.workflow_stage}, active_turn_stage={session.active_turn_stage})"
    )
    response = await session.ask(query)
    print("\nAssistant>\n")
    print(extract_last_message_text(response))
    print(
        f"\n[state] workflow_stage={session.workflow_stage}, "
        f"active_turn_stage={session.active_turn_stage}"
    )
    if show_state_json:
        print("\nFull state>\n")
        print(json.dumps(_json_safe(response), ensure_ascii=False, indent=2))


def _json_safe(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: _json_safe(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_json_safe(item) for item in data]
    return getattr(data, "content", str(data))

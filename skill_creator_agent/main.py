from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import sys
from typing import Any

from skill_creator_agent.paths import project_path

DEFAULT_CONFIG_PATH = project_path("config.yaml")
DEFAULT_OUTPUT_ROOT = project_path(".tmp", "data_agent_multiturn")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the interactive CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Interactive multi-turn CLI for skill_creator via Ferry DataAgent.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
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
        default=str(DEFAULT_OUTPUT_ROOT),
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


def main(argv: list[str] | None = None) -> int:
    """Run the synchronous CLI entrypoint."""
    _ensure_ferry_importable()
    return asyncio.run(async_main(argv))


async def async_main(argv: list[str] | None = None) -> int:
    """Run the async CLI entrypoint."""
    from skill_creator_agent.orchestration.session import build_data_agent_session

    _configure_logging()
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

    logger.info("Skill Creator DataAgent CLI")
    logger.info("- ferry config: %s", session.ferry_config_path)
    logger.info("- session_id:   %s", session.session_id)
    logger.info("- output_path:  %s", session.output_path)
    logger.info("- skills_root:  %s", session.runtime.settings.skills_root)
    logger.info(
        "- graph:        %s",
        "enabled" if session.runtime.settings.graph_enabled else "disabled",
    )
    if session.runtime.settings.graph_enabled:
        logger.info("- graph_url:    %s", session.runtime.settings.graph_base_url)
    logger.info("")

    if args.turn:
        for turn in args.turn:
            await _run_turn(session, turn, show_state_json=args.show_state_json)
        return 0

    logger.info("Commands: /skills, /config, /stage, /reset, /help, /quit")
    while True:
        try:
            user_input = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            logger.info("\nBye.")
            return 0

        if not user_input:
            continue
        if user_input == "/quit":
            logger.info("Bye.")
            return 0
        if user_input == "/help":
            logger.info("Commands: /skills, /config, /stage, /reset, /help, /quit")
            continue
        if user_input == "/skills":
            logger.info("%s", json.dumps(session.runtime.list_skills(), ensure_ascii=False, indent=2))
            continue
        if user_input == "/config":
            logger.info("%s", session.ferry_config_path)
            continue
        if user_input == "/stage":
            logger.info(
                "%s",
                json.dumps(
                    {
                        "workflow_stage": session.workflow_stage,
                        "active_turn_stage": session.active_turn_stage,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            continue
        if user_input == "/reset":
            previous = session.session_id
            session.reset()
            logger.info("Session reset: %s -> %s", previous, session.session_id)
            logger.info("New output_path: %s", session.output_path)
            continue

        await _run_turn(session, user_input, show_state_json=args.show_state_json)


def _ensure_ferry_importable() -> None:
    """Ensure Ferry is installed in the current Python environment."""
    if _can_import_ferry():
        return

    raise RuntimeError(
        "Ferry is not available in the current Python environment. "
        "Install Ferry into this interpreter before starting the CLI."
    )


def _can_import_ferry() -> bool:
    """Return whether the current interpreter can import Ferry and its dependencies."""
    try:
        importlib.import_module("ferry.interface.sdk.agent")
        return True
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("ferry"):
            return False
        raise RuntimeError(
            "Ferry is present in the current Python environment, but a required dependency is missing: "
            f"{exc.name}. Install Ferry dependencies in this interpreter first."
        ) from exc


def _configure_logging() -> None:
    """Configure plain-text CLI logging for interactive terminal output."""
    if logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


async def _run_turn(session: Any, query: str, *, show_state_json: bool) -> None:
    from skill_creator_agent.orchestration.session import extract_last_message_text

    logger.info(
        "\n[run_id=%s] sending... (workflow_stage=%s, active_turn_stage=%s)",
        session.next_run_id,
        session.workflow_stage,
        session.active_turn_stage,
    )
    response = await session.ask(query)
    logger.info("\nAssistant>\n")
    logger.info("%s", extract_last_message_text(response))
    logger.info(
        "\n[state] workflow_stage=%s, active_turn_stage=%s",
        session.workflow_stage,
        session.active_turn_stage,
    )
    if show_state_json:
        logger.info("\nFull state>\n")
        logger.info("%s", json.dumps(_json_safe(response), ensure_ascii=False, indent=2))


def _json_safe(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: _json_safe(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_json_safe(item) for item in data]
    return getattr(data, "content", str(data))

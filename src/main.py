import argparse
import asyncio
import logging
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import get_settings
from src.pipeline.orchestrator import PipelineOrchestrator


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def cmd_run(resume: bool = False) -> int:
    settings = get_settings()
    orchestrator = PipelineOrchestrator(settings)
    await orchestrator.run(resume=resume)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ozon Analytics Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the full pipeline")
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    run_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.command == "run":
        setup_logging(getattr(args, "verbose", False))
        return asyncio.run(cmd_run(resume=getattr(args, "resume", False)))

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

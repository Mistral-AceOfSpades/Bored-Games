from __future__ import annotations

import argparse
from pathlib import Path

from vibe.game_tutor.orchestrator import MistralVibeOrchestrator
from vibe.game_tutor.webapp import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Game tutor orchestrator and local UI server.")
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser("generate", help="Generate artifacts from a rules file")
    generate_parser.add_argument("rules", type=Path, help="Path to raw rules file")
    generate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("game-tutor"),
        help="Output directory for generated artifacts",
    )

    serve_parser = subparsers.add_parser("serve", help="Run local upload UI")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument(
        "--storage",
        type=Path,
        default=Path("game-tutor/generated"),
        help="Local storage for uploads and generated sessions",
    )

    parser.add_argument("legacy_rules", nargs="?", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("legacy_output", nargs="?", type=Path, help=argparse.SUPPRESS)

    args = parser.parse_args()

    match args.command:
        case "generate":
            manifest = MistralVibeOrchestrator().run(args.rules, args.output)
            print(f"Generated artifacts for {manifest['parsed_rules']['game_name']} at {args.output}")
        case "serve":
            run_server(host=args.host, port=args.port, storage_root=args.storage)
        case _:
            if args.legacy_rules is None:
                parser.print_help()
                return
            output = args.legacy_output or Path("game-tutor")
            manifest = MistralVibeOrchestrator().run(args.legacy_rules, output)
            print(f"Generated artifacts for {manifest['parsed_rules']['game_name']} at {output}")


if __name__ == "__main__":
    main()

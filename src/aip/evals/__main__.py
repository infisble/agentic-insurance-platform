import argparse
import asyncio
import sys
from pathlib import Path

from aip.agents.stack import AgentSettings, make_gateway
from aip.evals import extraction


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=extraction.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="suite", required=True)
    p = sub.add_parser("extraction")
    p.add_argument("--extractor", choices=["baseline", "llm"], default="baseline")
    p.add_argument("--parties", type=int, default=200, help="size of the generated golden set")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--limit", type=int)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--model")
    p.add_argument("--gate", action="store_true", help="exit 1 if a gate fails")
    p.add_argument("--out", type=Path, default=Path("evals/reports"))
    args = parser.parse_args()

    settings = AgentSettings()
    gateway = make_gateway(settings) if args.extractor == "llm" else None
    model = (args.model or settings.llm_model) if args.extractor == "llm" else None
    summary = asyncio.run(
        extraction.run(
            args.extractor, args.parties, args.seed, args.limit, args.concurrency, gateway, model
        )
    )
    path = extraction.write_report(summary, args.out)
    print(extraction.render(summary))
    print(f"report: {path}")
    if args.gate and (fails := extraction.gate_failures(summary)):
        print("GATE FAILED: " + "; ".join(fails))
        sys.exit(1)


if __name__ == "__main__":
    main()

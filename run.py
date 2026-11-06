"""CLI: python run.py --data data --out outputs/run1 [--mode llm|heuristic|both]"""
import argparse
from pathlib import Path

import yaml

from promo.parser import load_dir
from promo.pipeline import run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data", help="folder of episode .txt files")
    ap.add_argument("--out", default="outputs/run")
    ap.add_argument("--mode", default=None, choices=["llm", "heuristic", "both"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--episodes", default=None, help="e.g. 1-10 to run a subset")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    eps = load_dir(args.data)
    if args.episodes:
        a, b = map(int, args.episodes.split("-"))
        eps = [e for e in eps if a <= e.number <= b]
    if not eps:
        raise SystemExit(f"no episodes found in {args.data}")
    run(eps, cfg, Path(args.out), mode=args.mode or cfg.get("mode", "llm"))


if __name__ == "__main__":
    main()

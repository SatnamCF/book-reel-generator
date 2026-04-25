"""CLI entry point: python -m src.main "Book Title" --duration 30"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import llm_script, render


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate an Instagram Reel summary video for a book.")
    p.add_argument("book", help='Book title, e.g. "Atomic Habits"')
    p.add_argument("--duration", type=int, default=30, choices=[15, 30, 45, 60, 90],
                   help="Target video length in seconds (default: 30)")
    p.add_argument("--output", type=Path, default=None,
                   help="Output MP4 path (default: ./out/<slug>.mp4)")
    p.add_argument("--work-dir", type=Path, default=Path("./out/_work"),
                   help="Directory for intermediate slide PNGs and voiceovers")
    p.add_argument("--content-json", type=Path, default=None,
                   help="Skip the LLM call; load slide JSON from this file")
    p.add_argument("--save-content", type=Path, default=None,
                   help="Also save the LLM JSON to this path")
    return p.parse_args()


def _slug(s: str) -> str:
    keep = "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")
    while "__" in keep:
        keep = keep.replace("__", "_")
    return keep or "reel"


def main() -> int:
    args = parse_args()

    if args.content_json:
        content = json.loads(args.content_json.read_text(encoding="utf-8"))
        print(f"Loaded slide content from {args.content_json}")
    else:
        print(f"Generating script for '{args.book}' ({args.duration}s) via Claude...")
        content = llm_script.generate(args.book, args.duration)
        print(f"  -> {len(content['slides'])} slides, by {content.get('author', '?')}")
        if args.save_content:
            args.save_content.parent.mkdir(parents=True, exist_ok=True)
            args.save_content.write_text(json.dumps(content, indent=2), encoding="utf-8")
            print(f"  -> saved JSON to {args.save_content}")

    out_path = args.output or Path(f"./out/{_slug(content.get('book', args.book))}_{args.duration}s.mp4")
    print(f"Rendering video -> {out_path}")
    result = render.render_all(content, args.duration, args.work_dir, out_path)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

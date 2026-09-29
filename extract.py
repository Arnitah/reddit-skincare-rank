"""Stage 2: send comments to Claude in batches and save one record per mention.

Usage:
    export ANTHROPIC_API_KEY=...
    python extract.py sample/threads out/mentions.jsonl
    python extract.py sample/threads out/mentions.jsonl --dry-run   # show the first request, no API call
"""
import argparse
import json
import sys
from pathlib import Path

from threads import load_threads

ROOT = Path(__file__).parent
PROMPT = (ROOT / "extraction/prompt.md").read_text(encoding="utf-8")
SCHEMA = json.loads((ROOT / "extraction/mention.schema.json").read_text(encoding="utf-8"))
ITEM = SCHEMA["properties"]["mentions"]["items"]
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
BATCH = 50


def known_names() -> list[str]:
    aliases = json.loads((ROOT / "aliases.json").read_text(encoding="utf-8"))
    return sorted(set(aliases.values()))


def build_request(batch: list[dict], model: str) -> dict:
    numbered = "\n\n".join(f"[{i}] {c['body']}" for i, c in enumerate(batch))
    user = (
        "Known canonical names:\n" + "\n".join(known_names())
        + "\n\nComments:\n\n" + numbered
    )
    return {
        "model": model,
        "max_tokens": 8000,
        "system": PROMPT,
        "tools": [{"name": "record_mentions", "description": "Record every mention found.", "input_schema": SCHEMA}],
        "tool_choice": {"type": "tool", "name": "record_mentions"},
        "messages": [{"role": "user", "content": user}],
    }


def validate(record: dict, batch_size: int) -> list[str]:
    errors = []
    for key in ITEM["required"]:
        if key not in record:
            errors.append(f"missing {key}")
    for key, spec in ITEM["properties"].items():
        if "enum" in spec and record.get(key) not in spec["enum"]:
            errors.append(f"{key}={record.get(key)!r} not allowed")
    if not 0 <= record.get("comment_index", -1) < batch_size:
        errors.append("comment_index out of range")
    return errors


def parse_response(content: list, batch: list[dict], thread: dict) -> tuple[list[dict], list[str]]:
    """Turn the tool call into mention rows tied to comment ids and hashed authors."""
    tool = next((b for b in content if getattr(b, "type", b.get("type") if isinstance(b, dict) else None) == "tool_use"), None)
    if tool is None:
        return [], ["no tool call in response"]
    data = tool.input if hasattr(tool, "input") else tool["input"]
    rows, problems = [], []
    for rec in data.get("mentions", []):
        errs = validate(rec, len(batch))
        if errs:
            problems.append(f"{rec.get('entity_raw')}: {', '.join(errs)}")
            continue
        comment = batch[rec["comment_index"]]
        rows.append({
            "thread_id": thread["thread_id"],
            "subreddit": thread["subreddit"],
            "url": thread["url"],
            "comment_id": comment["id"],
            "author_hash": comment["author_hash"],
            **{k: v for k, v in rec.items() if k != "comment_index"},
        })
    return rows, problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("threads_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    threads = load_threads(args.threads_dir)
    total = sum(len(t["comments"]) for t in threads)
    print(f"{len(threads)} threads, {total} comments")

    if args.dry_run:
        t = threads[0]
        print(json.dumps(build_request(t["comments"][:BATCH], args.model), indent=2)[:4000])
        return

    import anthropic
    client = anthropic.Anthropic()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.out.open("w", encoding="utf-8") as f:
        for t in threads:
            for start in range(0, len(t["comments"]), BATCH):
                batch = t["comments"][start:start + BATCH]
                for attempt in (1, 2):
                    resp = client.messages.create(**build_request(batch, args.model))
                    rows, problems = parse_response(resp.content, batch, t)
                    if not problems or attempt == 2:
                        break
                for p in problems:
                    print(f"  skipped: {p}", file=sys.stderr)
                for r in rows:
                    f.write(json.dumps(r) + "\n")
                written += len(rows)
                print(f"  {t['thread_id']} [{start}:{start + len(batch)}] -> {len(rows)} mentions")
    print(f"wrote {written} mentions to {args.out}")


if __name__ == "__main__":
    main()

"""Load threads from the hand-collection text format (or JSON) into one structure.

Text format (one file per thread, see sample/threads/):

    subreddit: SkincareAddiction
    title: Post title
    url: https://www.reddit.com/r/...
    date: 2026-09-01
    ---
    u/someuser
    Comment text, any number of lines.
    ---
    u/another
    Next comment.

The post body itself can be the first comment block.
"""
import hashlib
import json
import os
from pathlib import Path

SALT = os.environ.get("RSR_SALT", "change-me-before-real-data")


def hash_author(name: str) -> str:
    name = name.strip().lower().removeprefix("u/")
    return hashlib.sha256((SALT + name).encode()).hexdigest()[:16]


def parse_text(path: Path) -> dict:
    header, *blocks = path.read_text(encoding="utf-8").split("\n---")
    meta = {}
    for line in header.strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip().lower()] = val.strip()
    comments = []
    for i, block in enumerate(b.strip() for b in blocks):
        if not block:
            continue
        lines = block.splitlines()
        author = "unknown"
        if lines[0].strip().startswith("u/"):
            author, lines = lines[0].strip(), lines[1:]
        body = "\n".join(lines).strip()
        if body and body not in ("[deleted]", "[removed]"):
            comments.append({"id": f"{path.stem}-{i}", "author_hash": hash_author(author), "body": body})
    return {
        "thread_id": path.stem,
        "subreddit": meta.get("subreddit", ""),
        "title": meta.get("title", ""),
        "url": meta.get("url", ""),
        "date": meta.get("date", ""),
        "comments": comments,
    }


def parse_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for c in data["comments"]:
        if "author_hash" not in c:
            c["author_hash"] = hash_author(c.pop("author", "unknown"))
    data["comments"] = [c for c in data["comments"] if c["body"] not in ("[deleted]", "[removed]")]
    return data


def load_threads(folder: Path) -> list[dict]:
    threads = []
    for path in sorted(folder.iterdir()):
        if path.suffix == ".txt":
            threads.append(parse_text(path))
        elif path.suffix == ".json":
            threads.append(parse_json(path))
    return threads

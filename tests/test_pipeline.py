"""Offline test: parse the synthetic thread, validate a canned Claude response, score it.

Run: python tests/test_pipeline.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extract import build_request, parse_response  # noqa: E402
from score import score  # noqa: E402
from threads import load_threads  # noqa: E402

threads = load_threads(ROOT / "sample/threads")
t = threads[0]
assert len(t["comments"]) == 12, len(t["comments"])
assert t["comments"][0]["author_hash"] == t["comments"][7]["author_hash"], "same user should hash the same"
assert "test_a" not in json.dumps(t), "usernames must not survive parsing"

req = build_request(t["comments"], "claude-haiku-4-5-20251001")
assert req["tool_choice"]["name"] == "record_mentions"

fake = [json.loads((ROOT / "tests/fake_response.json").read_text())]
rows, problems = parse_response(fake, t["comments"], t)
assert len(rows) == 15, len(rows)
assert len(problems) == 1 and "out of range" in problems[0], problems

res = score(rows, min_users=2)
top = {r["entity"]: r for r in res["ranked"]}

bha = top["Paula's Choice 2% BHA Liquid Exfoliant"]
assert bha["unique_users"] == 2, "test_a mentioned it twice but counts once"
assert bha["net"] == 0.0 and bha["reaction_rate"] == 0.5

boj = top["Beauty of Joseon Relief Sun Rice + Probiotics SPF 50+"]
assert boj["unique_users"] == 3 and boj["score"] == 2.0

assert top["azelaic acid"]["unique_users"] == 2, "the question must not count"
assert "COSRX Advanced Snail 96 Mucin Power Essence" not in top, "secondhand must not count"
assert "tretinoin" in res["emerging"]

(ROOT / "out").mkdir(exist_ok=True)
with (ROOT / "out/mentions_synthetic.jsonl").open("w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
print("all checks passed")

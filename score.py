"""Stage 4: rank entities from extracted mentions.

Usage:
    python score.py out/mentions.jsonl out/ [--min-users 5]

Method (see build plan):
  - only firsthand mentions count
  - each user counts once per entity, using their latest mention
  - positive = 1 P, negative = 1 N, mixed = 0.5 P + 0.5 N, neutral = 0
  - net = (P - N) / U, score = U * (1 + net) / 2
  - ranked when U >= min_users, otherwise "emerging"
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
WEIGHTS = {"positive": (1, 0), "negative": (0, 1), "mixed": (0.5, 0.5), "neutral": (0, 0)}
REACTIONS = {"breakout", "irritation"}


def load_aliases() -> dict:
    return {k.lower(): v for k, v in json.loads((ROOT / "aliases.json").read_text(encoding="utf-8")).items()}


def canonical(m: dict, aliases: dict, unknown: set) -> str:
    for key in (m["entity_raw"], m["canonical_guess"]):
        hit = aliases.get(key.strip().lower())
        if hit:
            return hit
    if m["canonical_guess"] not in aliases.values():
        unknown.add(m["canonical_guess"])
    return m["canonical_guess"]


def score(mentions: list[dict], min_users: int) -> dict:
    aliases = load_aliases()
    unknown: set[str] = set()
    latest: dict[str, dict[str, dict]] = defaultdict(dict)  # entity -> author -> mention
    meta: dict[str, dict] = {}
    for m in mentions:
        if m["experience"] != "firsthand":
            continue
        name = canonical(m, aliases, unknown)
        latest[name][m["author_hash"]] = m  # later lines overwrite = latest mention
        meta.setdefault(name, {"type": m["entity_type"], "category": m["category"]})

    rows = []
    for name, by_user in latest.items():
        users = list(by_user.values())
        u = len(users)
        p = sum(WEIGHTS[x["sentiment"]][0] for x in users)
        n = sum(WEIGHTS[x["sentiment"]][1] for x in users)
        net = (p - n) / u
        reacted = sum(1 for x in users if x["reaction_flag"] in REACTIONS)
        rows.append({
            "entity": name,
            **meta[name],
            "unique_users": u,
            "positive": p,
            "negative": n,
            "net": round(net, 2),
            "score": round(u * (1 + net) / 2, 2),
            "reaction_rate": round(reacted / u, 2),
            "subreddits": sorted({x["subreddit"] for x in users}),
            "reasons_for": [x["reason"] for x in users if x["sentiment"] == "positive"][:3],
            "reasons_against": [x["reason"] for x in users if x["sentiment"] == "negative"][:3],
            "skin_contexts": sorted({x["skin_context"] for x in users if x["skin_context"]}),
            "threads": sorted({x["url"] for x in users if x["url"]}),
        })

    ranked = sorted((r for r in rows if r["unique_users"] >= min_users), key=lambda r: -r["score"])
    emerging = sorted((r for r in rows if r["unique_users"] < min_users), key=lambda r: -r["score"])
    by_category = defaultdict(list)
    for r in ranked:
        by_category[r["category"]].append(r["entity"])
    polarizing_floor = max(15, min_users)
    return {
        "min_users": min_users,
        "ranked": ranked,
        "by_category": dict(by_category),
        "polarizing": [r["entity"] for r in ranked if r["unique_users"] >= polarizing_floor and abs(r["net"]) <= 0.2],
        "most_reactions": [r["entity"] for r in sorted(ranked, key=lambda r: -r["reaction_rate"]) if r["reaction_rate"] > 0],
        "emerging": [r["entity"] for r in emerging],
        "needs_alias_review": sorted(unknown),
    }


def to_markdown(res: dict) -> str:
    out = [f"# Rankings (min {res['min_users']} unique users)\n",
           "| # | Entity | Category | Users | Net | Score | Reaction rate |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(res["ranked"], 1):
        out.append(f"| {i} | {r['entity']} | {r['category']} | {r['unique_users']} | {r['net']:+.2f} | {r['score']} | {r['reaction_rate']:.0%} |")
    for label, key in (("Polarizing", "polarizing"), ("Most reactions", "most_reactions"),
                       ("Emerging (too few users to rank)", "emerging"), ("New names to review", "needs_alias_review")):
        out.append(f"\n**{label}:** " + (", ".join(res[key]) or "none"))
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mentions", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--min-users", type=int, default=5)
    args = ap.parse_args()
    mentions = [json.loads(line) for line in args.mentions.read_text(encoding="utf-8").splitlines() if line.strip()]
    res = score(mentions, args.min_users)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "rankings.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (args.out_dir / "rankings.md").write_text(to_markdown(res), encoding="utf-8")
    print(to_markdown(res))


if __name__ == "__main__":
    main()

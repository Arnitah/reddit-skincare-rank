# reddit-skincare-rank

Read-only research tool that ranks the skincare products and ingredients Reddit communities recommend, weighted by sentiment and unique users, with usernames hashed and links back to source threads.

## Reddit data use

- **Read-only.** Never posts, comments, votes, messages, or joins communities.
- **Public content only** from r/SkincareAddiction, r/AsianBeauty, r/30PlusSkinCare, r/Sunscreen, and r/acne.
- **Usernames are never stored.** They're replaced with a salted hash when a thread is loaded (see `threads.py`).
- **Deleted or removed comments are dropped** on each run.
- **No resale, sharing, or AI model training** on Reddit data.
- **Results are aggregated** (counts and short paraphrased reasons) with links back to the original threads.
- Low volume: a few thousand comments per topic, refreshed at most weekly.

## How it works

```
threads  ->  extract.py (Claude)  ->  mentions.jsonl  ->  score.py  ->  rankings
```

| File | What it does |
| --- | --- |
| `threads.py` | Loads threads and replaces usernames with salted hashes. |
| `extraction/prompt.md` | Instructions for identifying product and ingredient mentions. |
| `extraction/mention.schema.json` | The exact structure each mention must follow. |
| `extract.py` | Processes comments in batches of 50 and validates every record. |
| `aliases.json` | Maps name variants to one canonical product name. |
| `score.py` | Ranks by unique users: firsthand mentions only, one vote per user, `score = U × (1 + net) / 2`. |
| `db/schema.sql` | Postgres tables and views that compute scores at read time. |
| `tests/test_pipeline.py` | Offline tests using synthetic data. |

## Run the tests

```bash
pip install anthropic
python tests/test_pipeline.py
```

## Notes

- `sample/threads/synthetic-demo-01.txt` and `tests/fake_response.json` are invented test data, not Reddit content.
- API keys and the hashing salt are set as environment variables and never committed.

# Bench — Phoenix analysis mirror (READ-ONLY, NON-CANONICAL)

This bench renders the canonical store for human QA. It is a mirror, never
source of truth:

- it never appears in any publication or release path (guard-noted in
  tests/README.md)
- re-feeds are idempotent by construction (dataset item id = attempt_id)
- killing `./data/` loses nothing that can't be re-fed

Run: `docker compose up -d phoenix`, then `uv run bench/feed.py --store <store_root>`.

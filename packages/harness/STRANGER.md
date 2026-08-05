# STRANGER.md — reproduce our figures without trusting us

You need: a fresh clone, Python ≥3.14 (or docker), `duckdb`. Nothing else.
Not our CI. Not our credentials. Not our environment.

## One command

```bash
python bundles/<figure_id>/<ladder>/pipeline/run.py --slice bundles/<figure_id>/<ladder>/slice --out out/
```

Compare `out/` to `bundles/<figure_id>/<ladder>/expected.json` (hash per figure).
Default tolerance: **zero** — figures are byte-planned deterministic. If bytes
differ, the printed environment diff tells you which of {python, platform} you
diverge on; every divergence is a named artifact, never "nothing matches".

## What the bundle is

- `slice/` — the exact data slice the figure was computed from
- `rules/` — the pinned classification ruleset (arbitrary semantics live here, not in our code)
- `pipeline/` — a verbatim copy of the figure pipeline code. No git reference.
- `manifest.json` — per-file sha256, plus the `inputs` block (store snapshot,
  ruleset version, code commit, seeds, ladder level)

## The ladder

`small` always runs on commodity CPU in <1 h. `medium` = larger slice, same
code. `full` = the campaign dataset slice (once the Act I campaign has run).

## If you reproduce us

Tell us: file an issue with your env diff. Affiliation standard for being
counted as an independent reproduction: no shared employer / co-authorship /
repo history with the builder — self-attestation + public-record check (FR-8).

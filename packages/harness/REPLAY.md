# Replay bundles (Tier-1, stranger-facing one-pager)

A **replay bundle** is a self-contained directory. It carries:

- `slice/` — the exact store slice (parquet/json) the figures were computed from
- `rules/` — the pinned ruleset artifacts used by the pipeline
- `pipeline/` — a verbatim COPY of the figure pipeline code + its config
- `manifest.json` — per-file hashes + the inputs block (which code, which data, which seeds)

You need nothing else: not our repo, not our history, not our CI. The pipeline
code inside the bundle is the only code that runs.

## Reproduce

```bash
python pipeline/run.py --slice slice/ --out out/
```

Then compare `out/` hashes to `expected_figures.json` published alongside
(or let `store.replay_check` do it). Default tolerance: ZERO — byte-identical
figures or a divergence report naming the exact artifact that moved.

## Divergence

A mismatch prints an environment-diff (python version, platform). It means one
of: your host differs in a way the authors didn't pin (report it), the bundle
was tampered with (hashes don't match files), or the publication is wrong — in
each case the erratum protocol is the route, not quiet re-runs.

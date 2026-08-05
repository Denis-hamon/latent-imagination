# Dry-run report — Act I

| Check | Result | Evidence |
| --- | --- | --- |
| Tier-1 recompute from fresh env (scripts/act1/dry-run.sh on the published bundle) | ☐ pending (needs a published Act I bundle — links 2.7 campaign) | command + stdout saved below |
| NFR-R1 bindings resolve (commit, data versions, env, seeds) | ☐ | manifest paths |
| NFR-S1 vocabulary hold (no bare "world model"; numbers ship with reproduction path) | ✅ pass at authoring | `git grep -i "world model"` shows only qualified/doctrine-register use (README + docs) |
| FR-9 no-judge audit (static) | ✅ pass | `uv run pytest tests/guards/test_no_judge.py -q` (3 tests, incl. function proof) |
| Five-second headline, non-specialist read | ☐ HUMAN step — name+date: 〈owner, at release time〉 | printed headline text |
| quarantine/flaky shares under cap | ☐ | figure manifests |

> The dry-run is REHEARSED here on fixtures; it is EXECUTED on the real Act I
> bundle as part of the 2.7 campaign close-out. The executed instance of this
> report is filled then, signed by the operator.

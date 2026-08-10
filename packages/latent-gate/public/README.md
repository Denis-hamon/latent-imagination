# latent-gate — pre-flight consequence scoring for code patches

*An MCP/HTTP service that answers one narrow question: **"will this patch make
the failing tests pass?"** — before you run anything. When it doesn't know,
it says so.*

## What it is

A scoring endpoint for LLM-generated patches. You send the current state
(problem / failing test names), the proposed diff **as the model wrote it**,
and optionally the goal (test statement). You get back a pass-probability, a
confidence tier, and an advice that is allowed to be **`abstain`**.

It is deliberately narrow. It does not review style, does not fix your patch,
does not regenerate code. It estimates consequence, in representation space,
from a pool of real executed patches, and it publishes its own measurement
harness so you can verify our numbers on your machine.

| tool (MCP & HTTP) | input | output |
|---|---|---|
| `score_patch` | state, diff, goal (opt.), exclude_task (opt.) | `p_pass`, `confidence`, `confidence_tier` (high/mid/low), `advice` ∈ likely-pass / lean-pass / lean-fail / likely-fail / **abstain** / goal-free-only |
| `risk_scan` | state, diff | goal-free risk (near-fail vs near-pass attractors) — rank, not verdict |
| `near_misses` | state, k | k nearest historical patches with their real executed outcome |
| `report_outcome` | call_id, passed | append-only, hashed; grows the pool by validated batches — never online mutation |
| `health` / `claims` | — | status, pool & model hashes, signed claims |

## The measured numbers (with confidence intervals, not vibes)

Campaign-measured on the production pool, leave-one-task-out, all decisions
out-of-fold (145 real executed LLM patches, 78 tasks, SWE-smith-derived):

| coverage (most confident first) | accuracy | Wilson 95 % |
|---|---|---|
| 100 % | 0.710 | [0.632, 0.778] |
| 50 % | 0.833 | [0.731, 0.902] |
| 25 % | 0.944 | [0.819, 0.985] |
| 20 % | 0.966 | [0.828, 0.994] |

On the public eval pack (16 frozen tasks, 50 candidates, served with
`exclude_task` — true hold-out): 0.880 [0.762, 0.944] at full coverage,
1.000 [0.867, 1.000] at 50 %. That pack population is narrower than the
general pool — both curves are published; believe the worse one.

**What "abstain" buys you, concretely:** at ~25 % coverage the instrument has
never been measurably wrong on its own pool. The service therefore refuses to
give a pass/fail direction below the confidence quantiles — a *measured*
behavior, with the curve above as the contract.

## What it does NOT claim

- No "this makes your LLM write better code". A pre-registered RCT of
  consequence-context injection was **negative** (published, sealed). What we
  sell is *selection with abstention*, not augmentation.
- No guarantee outside the measured regime: single-hunk diffs, Python-heavy
  library tasks, one generator family. Outside that, watch the confidence tier,
  not the advice.
- No free scorer: choosing among K candidates by this score alone was measured
  to be chance-level at n=32 (published negative too). The score is a gate, not
  an oracle.

## Verify it yourself (falsifiable by construction)

```bash
# serve the public build (see Dockerfile), then:
python eval-pack/run_eval.py --base-url http://localhost:8080
```

`run_eval.py` calls the service with `exclude_task=<task>` for every candidate:
the server removes that whole task from its pool before scoring, so the curve
you reproduce is leave-one-task-out by construction. Only numpy-free stdlib
Python on the client side. If our numbers are wrong, this script is the knife.

## Integration

MCP (stdio) for Claude Code / opencode, and HTTP REST (`POST /v1/score_patch`,
`X-API-Key` header) for everything else. Latency ≈ 200-400 ms per call CPU
(measured); no LLM is called server-side — scoring is a 110 M-parameter encoder
plus a 3-parameter calibration.

## Honesty ledger (short)

Pool & model are hashed; the hashes are what `health` returns. Outcome reports
land append-only and are promoted to the pool by validated batches — your data
is never re-shared. Dependency stack is 100 % permissive (checked 2026-08-10
against the HF API): encoder `microsoft/unixcoder-base` Apache-2.0, fallback
encoders jina-code Apache-2.0 / CodeRankEmbed MIT, source corpus SWE-smith MIT.

Bugs, misuse reports, and the erratum protocol: see `governance/`.
*latent-imagination project — measuring first, publishing the negatives.*

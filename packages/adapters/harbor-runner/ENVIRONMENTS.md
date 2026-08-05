# Harbor env-model fit (addendum §E.4#2)

**Verdict (2026-08-05, dev-mode inspection):** Harbor 0.20 provisions task
environments as Docker containers keyed by its own task registry. Our F2P
Tasks need SWE-bench-style envs (pinned repo@commit + test suite), which match
Harbor's task-env mechanism. Remaining seam risk: our `extra.attempt` payload
(runtime fingerprints, f2p set, patch ref) must be attached via the trajectory
post-processing hook — verified by the sim fixture carrying exactly that payload.

Fallback if live fitting fails: drive envs ourselves (docker-compose per task),
use Harbor only for agent orchestration. Non-blocking for the sim path.

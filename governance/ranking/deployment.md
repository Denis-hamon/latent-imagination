# Ranking tool — deployment under gate policies (story 8.2)

**Same discipline as the advisory gate:**
- reads ONLY via the pinned snapshot hand-off port (`RankingServer.load` =
  `gate.ports.load_pinned_snapshot`, mandatory 64-hex pin);
- every ranking call logs `candidates_ranked` into the deployer-local fenced
  `decisions.jsonl` (never inside a store root);
- NO patch execution anywhere in `packages/tools-ranking` (construction-proof:
  the package holds no exec surface; CI guard scans it alongside gate for LLM
  clients; the surface-absence test runs word-boundary detection).

**OQ-10 consumption:** ranking a candidate set applies the gate's
prediction-target policy unchanged — `diff_touched` when the candidates touch
test paths, else the deployer's `LI_GATE_TEST_SELECTION`, else the call ABSTAINS
(abstention recorded in the log). A planning tool that invents a denominator
would break the same doctrine as a gate that does.

**Posture:** advisory planning aid (sub-bar baseline disclosed). Ranking never
promises outcome precision beyond the measured disclosure.

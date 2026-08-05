# Tests

Top-level suites: e2e, determinism replays, and the CI guard suite (`guards/`).

## Guard suite semantics (Story 1.5) — what "green" means

| Guard | Invariant | Mechanism | Function proven by | Failure code |
| --- | --- | --- | --- | --- |
| `network_deps` | AD-6: no network deps in core | static pyproject scan (deps + optional + groups) | synthetic violating fixture + exemption-proof test | fails assertions |
| `imports_lint` | AD-1: core never imports adapters | AST import graph | fixture with `import ots_anchor` in a fake core pkg | LI-CI-001 |
| `writer_inventory` | AD-4: only owning stages write | write-marker scan over `packages/**/src` | fixture with a write in a fake probe pkg | LI-CI-002 |
| `dependency_scan_gate` | AD-14: no LLM client in gate* | dependency names incl. groups | fixture gate pkg with `openai` | LI-CI-003 |
| `network_sandbox` | AD-6 runtime: no sockets in core suites | monkeypatched socket/`create_connection` | proof tests asserting the block raises | LI-CI-004 |
| `determinism_replay` | AD-7: labeling replay byte-identical | run-twice-compare hook | nondeterministic fixture must fail | assertion |
| `prereg_precedence` | FR-3: rulesets anchored before runs | store.validate ↔ prereg ledger rows | anchored-after-run fixture fails | precedence violation |

Rules for adding a guard: it MUST include a fixture/mutation test proving the
function (a gate proves the function, not its presence), carry one of the
LI-CI-00n codes, and land a row in this table.

# Labeling decision tree (FROZEN)

Editing this tree is a versioning event: bump `RULESET_VERSION`, re-anchor,
republish. Worked examples are part of the artifact (they test the tests).

## Order of evaluation

1. **Infrastructure failures first.** If raw test output contains infra markers
   (segfault, out-of-space, container start failure, network unreachable,
   ModuleNotFoundError …) → label `FALSE_START_INFRASTRUCTURE_FAILURE`. These DO
   count as False Starts (the metric measures agent-visible reality; subclasses
   exist for analysis, not exemption).
2. **Ambiguity.** Timeouts / killed / panics without a clear class → **do not
   label**. Route to quarantine (`AMBIGUOUS_OUTPUT`). Quarantined attempts exit
   BOTH numerator and denominator of ERBVE.
3. **Flip evidence.** Output contains a passing verdict of the task's F2P tests
   ("1 passed", "all tests passed", "0 failed") → label `VALID_EXECUTION`.
4. **Otherwise** → `FALSE_START_TESTS_RAN_NO_FLIP`.

## Worked examples (binding)

| Raw output contains | Label |
| --- | --- |
| `1 passed in 0.42s` | VALID_EXECUTION |
| `Segmentation fault (core dumped)` | FALSE_START_INFRASTRUCTURE_FAILURE |
| `FAILED tests/x.py::test_y` (no infra marker) | FALSE_START_TESTS_RAN_NO_FLIP |
| `connection timeout while resolving` | (quarantined) |
| `Killed by OOM watcher` | (quarantined) |

## Quarantine cap

Pre-registered cap: **10%** per figure/task-set. Exceeding halts the measurement
(QuarantineCapExceeded). Changing the cap = pre-registration change + re-anchor.

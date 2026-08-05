# ATIF → Execution Attempt mapping (closes addendum §E.4 item 4)

An ATIF `Step` is not itself an Execution Attempt. Mapping rule (v1):

- A Step becomes an ExecutionAttempt IFF it contains a `tool_calls` entry whose
  effect is a patch execution in a Task environment (function_name in the
  agreed set, e.g. `bash` with a test-running command).
- `attempt_window.start` = that step's ``timestamp`` (normalized to UTC);
  `attempt_window.end` = parent ``observation`` return time if known, else the
  NEXT step's timestamp, else == start.
- `raw_test_output_ref` = pointer to the observation's `content` written as a
  blob in data/landing (the content itself is never inlined into the canonical store).
- Steps without an execution call are context, not attempts.
- The mapping is DATA: the watchlist of function names lives in this adapter's
  config, not in the rule, so a new agent tool renamed "run_tests" is a config event.

Verified against: packages/core-schema/tests/fixtures/valid_trace_v1.json
(one Step-2 tool_call = one ExecutionAttempt, with end == timestamp of step 3).

# core-schema

Closed domain shapes (Task, ExecutionAttempt, Label, …), the ATIF v1.7 trace mirror, the store event envelope, and the single canonical identity derivation (AD-12).

## Version policy

Two `schema_version` fields coexist; they are unrelated:

- `ExecutionTrace.schema_version` — the ATIF **string** (`"ATIF-v1.7"`), mirroring the external trajectory format.
- `StoreEvent.schema_version` — ours, an **int** (`Literal[1]`). Bump policy below applies to ours.

**Bump rules (our int version)**:

1. Additive, optional fields only within a major version — never change a field's type or meaning.
2. Anything breaking (removed field, changed semantics, changed identity inputs) bumps the major and keeps v1 parsers importable (`core_schema.v1`-compat path or last-good tag is citable).
3. Migration determinism (AD-7): re-labeling old traces under a new schema version must reproduce prior labels byte-for-byte, or the migration PR fails its own replay test before merge.

Both validators are independent and each knows its own expected value; the LI-SCHEMA-001 gate belongs to the store envelope, ATIF-string checking belongs to the trace mirror.

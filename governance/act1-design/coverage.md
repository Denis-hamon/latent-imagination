# Coverage window policy (FR-6)

Coverage is an OUTPUT, never a promise.

Rules:
- every figure discloses the families/versions actually measured (registry-driven);
- anything attempted-but-unreachable (deprecated API, license-blocked archive) becomes a `coverage_gaps` entry in the registry entry for that source;
- figures print the coverage window line: "measured on: <families@versions>, <dates>".
No silent narrowing. A missing family is a documented absence, not a hidden one.

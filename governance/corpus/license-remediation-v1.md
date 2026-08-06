# License remediation procedure v1 (story 4.4, FR-17)

Trigger: a corpus constituent is found non-permissive AFTER publication of a
`corpus-release` (example precedent already on the books: GPL-3.0 / GPL-2.0 /
NOASSERTION items are refused at assembly — this procedure is for what slips anyway).

## Flow

1. **Remove** — the constituent pool is filtered out of the affected tier build
   inputs immediately (the same license allowlist machinery; no ad-hoc edits).
2. **Bump** — a NEW MAJOR corpus version (`corpus-v{N+1}`). Removal never mutates
   a published version (AD-3 append-only: the old artifact stays on WORM;
   republication of the old version stops, per the store contract).
3. **Republish** — rebuild: `corpus.publish()` re-assembles the affected tier
   artifact at a new `artifact_version`, then a new `corpus-release` manifest
   whose `license_inventory_hash` names the corrected inventory (the inventory
   json gains the entry's correction with evidence, itself versioned).
4. **Notify via the signature chain** — the erratum machinery
   (`governance/erratum-protocol.md` — negative-direction release) carries a
   notice naming: the removed constituent, the affected `corpus_version`(s),
   every published artifact whose `inputs` cite them (enumerable — inputs blocks
   are mandatory, AD-13), and the new release hash. Anything citing a superseded
   corpus version is INVALID for new claims until re-based.

## Verification duties

- CI: `tests/` fixture proves that emitting a corpus-release whose cited tier
  manifest's content drifted fails with LI-CORPUS-012 (story 4.4).
- The clean-tier build's per-item license resolution makes the constituent set
  enumerable — "which items does this repo touch" is a query, not archaeology.

## Bump rules owned here

MAJOR bump on: license removal/addition of a constituent class, exclusion-rule
change, hardening-policy change, schema change of any tier parquet, this
procedure's own material change. Patch-level (same MAJOR): documentation-only,
typo fixes in governance md companions.

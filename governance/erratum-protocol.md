# Erratum & revocation protocol (negative-direction releases)

A post-publication error (wrong figure, bad threshold, revoked certificate) is a
NEW artifact, never a rewrite:

1. The original chain stays. Immutability is not negotiable.
2. The erratum is assembled like any release (AD-5 chain), links the artifact(s)
   it corrects by hash, and gets its own anchor (negative-direction == same
   signature discipline, FR-21 notes).
3. Downstream: anything whose inputs block references the defective artifact is
   listed in the erratum as "invalidated" and must re-issue or stay visibly
   marked superseded in the next release.
4. Emergencies (e.g., leaked key) → rotation per KEYS.md, then a sweeping
   negative-direction release marking affected ranges.

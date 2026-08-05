# Keys — custody & rotation

Pre-first-signature scaffolding. The actual key material is provisioned at the
first release ceremony, never stored here.

- **Signer identity:** the builder (personal key, published at first release).
- **Custody:** private key on the signing host only; passphrase via env at the
  ceremony; CI signs nothing.
- **Rotation:** a rotation is a NEGATIVE-DIRECTION release: the new key's
  fingerprint + revocation of the old, hash-linked per the erratum protocol.
- **Evidence:** each signed release manifests the fingerprint it used;
  governance/erratum-protocol.md owns the downstream invalidation rules.

# OQ-2 resolution — what the encoder sees at encode time

Decision (registered 2026-08-05, probe seal):

- **Input document per attempt** = rendered patch diff + task statement + failed-test tail.
- **Feature extractor (baseline arm)** = `HashingVectorizer` (stateless, deterministic,
  zero model download, CPU-only) — the frozen-embedding equivalent that maximally
  respects kickoff constraints (AD-6 no network at compute time, reproducibility).

## Alternatives rejected, with reasons

- **Full repo slice embeddings** — per-attempt cost explodes; v1 budget (2× L40S
  ceiling) makes it cosmetic vs decisive. Also adds a heavyweight embedder that
  would need fetch-at-setup — doable but gratuitously heavy for the arbitration.
- **Test-file embeddings as features** — leakage: the test content is exactly what
  flips; giving the classifier the answer key rewrites the task.
- **A downloaded pretrained code embedder as "frozen embeddings"** — the boring
  baseline must be boring AND reproducible without a network roundtrip at compute.
  A pinned local model fetch would work (content-pinned artifact in landing) but
  adds a dependency whose marginal fairness value for a logistic-regression
  baseline is zero.

## Cost note (OQ-3-invisible path)

The JEPA arm's encoder trains locally on the node (never downloaded). Baseline
hashing is CPU-free; JEPA training is the only GPU workload and its budget envelope
is the registered one in design.toml.

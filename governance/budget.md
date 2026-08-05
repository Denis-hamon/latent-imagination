# Budget caps (PRD R10)

Caps are pre-registered. Hitting a cap shrinks scope with disclosure; never
silently biases coverage.

| Phase | Item | Cap (EUR) | On cap hit |
| --- | --- | --- | --- |
| 2 (Act I) | Field runs API spend (3 families × tasks) | TBD at Epic 2 kickoff — must be a number | drop 4th family, disclose in figure note |
| 2 (Act I) | B3 instance hours | TBD | stop between task batches, resume next window |
| 3 (probe) | GPU hours (baseline + JEPA arms) | TBD at Epic 3 kickoff | drop second JEPA arm (OQ-1 fallback documented) |
| 4 (corpus) | Harvest compute + storage growth | TBD at Epic 4 kickoff | pause harvest at last checkpoint, log partial tier |

Rules: numbers are written before the phase starts; exceeding is an event worth a memlog row.

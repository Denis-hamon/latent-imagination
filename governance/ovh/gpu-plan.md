# GPU node plan — the consolidated envelope

Spine rule (AD-10, amended 2026-08-05): **one single OVH Public Cloud instance
with 2× L40S (48 GB each)** carries everything:

- Harbor field runs + SWE-style task environments (local Docker, daytime)
- Probe/corpus training (NFR-C1 — the node IS the ceiling)
- prereg / gate / harness workloads are CPU-noise anywhere on it

Flavor string: pulled from the live catalog at provisioning
(`openstack flavor list | grep -i l40s`) — 2-GPU variant; record the exact
string here when provisioned:

    chosen flavor: 〈pending — fill at provisioning〉

There is NO separate B3/C3 instance anymore. Lazy-attach rule dies with it:
the GPU node is provisioned FIRST, because Epic 2 field runs already need
Docker; training joins it at Epic 3 without new infra.

## Budget cap hooks (PRD R10)

Per-phase caps in `governance/budget.md`. ~$3.60/h on-demand for this class —
kill between campaigns, log every start/stop in the evidence log of bootstrap.md.

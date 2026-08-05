# GPU plan — 2× L40S (NFR-C1)

Spine rule: single-node ≤ 2× L40S 48 GB. OVH PCI GPU instances: L40S flavors
(e.g. `l40s-…`; 1–4 GPUs per instance). Exact flavor string comes from the catalog
at provisioning time — pulled live, never hard-spec'd from memory:

```bash
curl -s "https://api.ovh.com/v1/publicCloud" -H "X-Ovh-Application-Key: $OVH_AK" # sanity
openstack flavor list | grep -i l40s   # pick the 2-GPU flavor string, paste below
```

Chosen flavor: 〈pending — fill at provisioning, Epic 3 required-by〉
Lazy attach: the GPU node is only provisioned when Epic 3 needs it (probe arms).

## Budget cap hooks (PRD R10)

Per-phase caps live in `governance/budget.md`. When a cap is hit the scope shrinks
(fewer families/tasks) WITH disclosure, never silent coverage reduction.

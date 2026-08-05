# OVH Public Cloud bootstrap (EU) — consolidated single-node envelope

Region default: Gravelines (GRA) unless flavor availability forces otherwise.
Target node: 2× L40S GPU instance (flavor from catalog at provisioning).

## Execution checklist (owner-run; needs OVH creds in env)

- [ ] `source .env.ovh` (OS_APPLICATION_CREDENTIAL_ID/SECRET or OVH_TOKEN — env only, never committed)
- [ ] `bash governance/ovh/provision.sh` — creates: Standard bucket, WORM bucket (Object Lock AT creation), **the GPU node**
- [ ] SSH in, run `scripts/setup-node.sh` (uv, Docker via official repo 29.7.1, NVIDIA toolkit, repo clone, guard suite green)
- [ ] Paste outputs below (instance id, bucket names, endpoints, `nvidia-smi` first screen) — evidence lives in this file, versioned

### Evidence log

| When | What | Verified by | Output snippet |
| --- | --- | --- | --- |
| 〈pending〉 | bucket standard created | `swift list` / manager | 〈pending〉 |
| 〈pending〉 | WORM bucket has Object Lock | `aws s3api get-object-lock-configuration` | 〈pending〉 |
| 〈pending〉 | GPU node up (2× L40S visible) | `openstack server show` + `nvidia-smi` | 〈pending〉 |
| 〈pending〉 | docker 29.7.1 on node | `docker --version` via ssh | 〈pending〉 |

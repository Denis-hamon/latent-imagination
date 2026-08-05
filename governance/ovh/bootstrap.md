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
| 2026-08-05 | GPU node reachable + 2× L40S + OS | `ssh WMEL-gpu-strong` | `2× NVIDIA L40S, 46068 MiB` · Ubuntu 26.04 LTS · 377Gi RAM · 423G free |
| 2026-08-05 | Docker 29.7.1 (official repo, worked around Ubuntu 26.04 having no "resolute" branch → noble fallback) | `docker --version` via ssh | `Docker version 29.7.1, build e9452d6` |
| 2026-08-05 | nvidia-container-toolkit + CDI | `dpkg -l \| grep nvidia-container` | `1.19.1-1` |
| 2026-08-05 | uv + Python | `uv --version`; `python3.14 --version` | `uv 0.12.2` *(0.12.2, not 0.12.1 — one patch newer than `.tool-versions`; CI pins handle)* · `Python 3.14.6` |
| 2026-08-05 | workspace sync + full suite on the node | `uv sync --locked --all-packages && uv run pytest -q` | `149 passed in 1.03s` |
| 2026-08-05 | Docker usable as ubuntu | `docker run --rm hello-world` | OK (after fresh ssh for group membership) |
| 〈pending〉 | bucket standard created | `swift list` / manager (needs OVH creds in env, still owner-run) | 〈pending〉 |
| 〈pending〉 | WORM bucket has Object Lock | `aws s3api get-object-lock-configuration` | 〈pending〉 |

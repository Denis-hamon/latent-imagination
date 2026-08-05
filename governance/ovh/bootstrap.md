# OVH Public Cloud bootstrap (EU)

Region default: Gravelines (GRA) unless flavor availability forces otherwise.
Confirm L40S zone availability from the catalog first: `governance/ovh/gpu-plan.md`.

## Execution checklist (owner-run; needs OVH creds in env)

- [ ] `source .env.ovh` (OS_APPLICATION_CREDENTIAL_ID/SECRET or OVH_TOKEN — env only, never committed)
- [ ] `bash governance/ovh/provision.sh` — creates: Standard bucket, WORM bucket (Object Lock AT creation), one B3-32-class instance
- [ ] Paste outputs below (instance id, bucket names, endpoints) — evidence lives in this file, versioned

### Evidence log

| When | What | Verified by | Output snippet |
| --- | --- | --- | --- |
| 〈pending〉 | bucket standard created | `swift list` / manager screenshot | 〈pending〉 |
| 〈pending〉 | WORM bucket has Object Lock | `aws s3api get-object-lock-configuration` | 〈pending〉 |
| 〈pending〉 | compute instance up | `openstack server show` | 〈pending〉 |
| 〈pending〉 | docker 29.7.1 on instance | `docker --version` via ssh | 〈pending〉 |

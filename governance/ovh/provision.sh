#!/usr/bin/env bash
# Latent Imagination — OVH Public Cloud provisioning (EU).
# Prereq: .env.ovh sourced (credentials live ONLY in env — AR-7).
# Idempotent where the APIs allow; re-runs print existing resources instead of failing.
set -euo pipefail

: "${OS_PROJECT_NAME:?OVH Public Cloud project name}"
: "${OS_REGION_NAME:=GRA11}"

echo "==> Object Storage — Standard bucket (bulk artifacts)"
openstack container create latent-imagination-artifacts || true

echo "==> Object Storage — WORM bucket for signed releases"
# Object Lock must be requested AT CREATION; cannot be added later (OVH S3 API).
aws --endpoint-url "https://s3.${OS_REGION_NAME}.io.cloud.ovh.net" \
  s3api create-bucket \
  --bucket latent-imagination-releases \
  --object-lock-enabled-for-bucket \
  --create-bucket-configuration "LocationConstraint=${OS_REGION_NAME}" || true

echo "==> Verify Object Lock enabled on the releases bucket"
aws --endpoint-url "https://s3.${OS_REGION_NAME}.io.cloud.ovh.net" \
  s3api get-object-lock-configuration \
  --bucket latent-imagination-releases

echo "==> Compute — the consolidated GPU node (2× L40S)"
echo "    (flavor string: from 'openstack flavor list | grep -i l40s' — pick the 2-GPU one)"
: "${GPU_FLAVOR:?export GPU_FLAVOR=<2x-l40s flavor string from catalog>}"
openstack server create \
  --flavor "$GPU_FLAVOR" \
  --image "Ubuntu 24.04" \
  --key-name "${OS_KEYPAIR:?ssh keypair name}" \
  --network Ext-Net \
  li-node-1

echo "==> Post-boot (run via ssh as ubuntu):"
cat <<'POST'
# Driver NVIDIA + Docker via OFFICIAL repos (apt docker.io ships 26/27.x, we need 29.7.1):
bash scripts/setup-node.sh   # from the cloned repo; it does driver, toolkit, docker pin, uv, clone, guard suite
POST

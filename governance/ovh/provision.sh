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

echo "==> Compute — B3 instance for Harbor runs + task envs"
openstack server create \
  --flavor b3-32 \
  --image "Ubuntu 24.04" \
  --key-name "${OS_KEYPAIR:?ssh keypair name}" \
  --network Ext-Net \
  li-field-runner-1

echo "==> Post-boot (run via ssh):"
cat <<'POST'
sudo apt-get update && sudo apt-get install -y docker.io
sudo docker --version   # must print 29.7.1 (record to bootstrap.md evidence log)
POST

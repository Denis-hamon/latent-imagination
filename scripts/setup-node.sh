#!/usr/bin/env bash
# setup-node.sh — bring a fresh Ubuntu 24.04 GPU node to the envelope spec (AD-10).
# Run as ubuntu (sudo available). Idempotent; safe to re-run.
set -euo pipefail

DOCKER_WANT="29.7.1"
PYTHON_WANT="3.14.6"
UV_WANT="0.12.1"
REPO="${1:-latent-imagination}"   # or absolute git URL when the repo is public

echo "==> APT baseline"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg git jq

echo "==> Docker Engine from the OFFICIAL Docker repo (apt docker.io ships old versions)"
CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
# Docker's repo may lag brand-new Ubuntu codenames; fall back to the last LTS branch.
case "$CODENAME" in
  noble|jammy|focal) DOCKER_DIST="$CODENAME" ;;
  *) DOCKER_DIST="noble" ;;
esac
echo "    (OS codename: $CODENAME → docker repo branch: $DOCKER_DIST)"
if ! docker --version 2>/dev/null | grep -q "$DOCKER_WANT"; then
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $DOCKER_DIST stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  docker --version | grep -q "$DOCKER_WANT" || {
    echo "NOTE: docker repo gave $(docker --version); pinning to $DOCKER_WANT requires 'apt-get install docker-ce=5:${DOCKER_WANT}*' style pin — log the actual version in governance/ovh/bootstrap.md evidence and amend the spine pin if it's a deliberate flex." >&2
  }
fi
sudo usermod -aG docker ubuntu 2>/dev/null || true

echo "==> NVIDIA driver + container toolkit (2× L40S)"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  sudo apt-get install -y ubuntu-drivers-common
  sudo ubuntu-drivers install nvidia:560
  echo "NOTE: reboot required after driver install — re-run this script after reboot."
fi
if ! dpkg -l | grep -q nvidia-container-toolkit; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt-get update -y
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
fi

echo "==> uv ${UV_WANT} + Python ${PYTHON_WANT} (user-managed)"
if [ ! -x "$HOME/.local/bin/uv" ] || ! "$HOME/.local/bin/uv" --version | grep -q "$UV_WANT"; then
  curl -fsSL https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$HOME/.local/bin" sh
fi
export PATH="$HOME/.local/bin:$PATH"
export UV_PYTHON_PREFERENCE=only-managed
uv python install "$PYTHON_WANT"

echo "==> Repo clone (read-only until OQ-6 makes it public)"
if [ -d "$HOME/$REPO/.git" ]; then
  git -C "$HOME/$REPO" pull --ff-only
else
  echo "NOTE: repo is still private. Push it to a private GitHub remote first, then:"
  echo "      git clone <private-url> $HOME/$REPO"
  echo "      (uses a deploy key or your PAT — never committed)"
fi

echo "==> Guard suite smoke"
if [ -d "$HOME/$REPO/.git" ]; then
  cd "$HOME/$REPO" && uv sync --locked --all-packages && uv run pytest -q
fi

echo "==> Node summary"
docker --version || true
nvidia-smi --query-gpu=name,memory.total --format=csv || true
uv --version
echo "Paste the three blocks above into governance/ovh/bootstrap.md evidence log."

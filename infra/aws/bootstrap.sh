#!/usr/bin/env bash
set -euxo pipefail
dnf install -y docker git python3
systemctl enable --now docker
usermod -aG docker ec2-user
install -d -m 700 -o ec2-user -g ec2-user /opt/releaseops/state
# Install Docker Compose separately using verified official release instructions.
# Register a private-repository GitHub runner with the custom label "releaseops".

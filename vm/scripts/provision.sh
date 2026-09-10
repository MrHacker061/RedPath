#!/usr/bin/env bash
set -euo pipefail

if ! command -v sshd >/dev/null 2>&1; then
  echo "The official Kali Vagrant box is missing sshd; refusing to leave an unreachable VM." >&2
  exit 1
fi

vagrant_home="$(getent passwd vagrant | cut -d: -f6)"
authorized_keys="${vagrant_home}/.ssh/authorized_keys"

if [[ -z "${vagrant_home}" || ! -s "${authorized_keys}" ]]; then
  echo "Vagrant's generated SSH key is not installed; refusing to disable password access." >&2
  exit 1
fi

install -d -m 0755 /etc/ssh/sshd_config.d
temporary_config="$(mktemp)"
trap 'rm -f "${temporary_config}"' EXIT

cat >"${temporary_config}" <<'EOF'
# Managed by the Headless Kali Terminal launcher.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
X11Forwarding no
AllowTcpForwarding yes
GatewayPorts no
PermitTunnel no
AllowAgentForwarding no
EOF

rm -f /etc/ssh/sshd_config.d/60-headless-kali.conf
install -m 0644 "${temporary_config}" /etc/ssh/sshd_config.d/00-headless-kali.conf
/usr/sbin/sshd -t
systemctl enable ssh >/dev/null
systemctl reload ssh || systemctl restart ssh

echo "Headless Kali SSH hardening is active (key authentication, localhost NAT)."

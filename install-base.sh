#!/usr/bin/env bash
# Teaching installer: fresh installation only. Does not enable sync, AI or public access.
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo bash install-base.sh" >&2
  exit 1
fi
if [[ -e /opt/air-health/app.py ]]; then
  echo "Existing installation detected. Stop and follow a reviewed upgrade plan." >&2
  exit 1
fi
for file in app.py static/index.html static/app.js static/app.css static/mobile.css air-health.service; do
  test -f "$file"
done
command -v python3 >/dev/null
command -v systemctl >/dev/null
id airhealth >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/air-health --shell /usr/sbin/nologin airhealth
install -d -o root -g root -m 0755 /opt/air-health /opt/air-health/static
install -d -o airhealth -g airhealth -m 0700 /var/lib/air-health
install -o root -g root -m 0644 app.py ai_broker.py web_gateway.py mcp_server.py /opt/air-health/
install -o root -g root -m 0644 static/index.html static/app.css static/mobile.css static/app.js /opt/air-health/static/
install -o root -g root -m 0644 air-health.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now air-health.service
echo "Base service enabled on 127.0.0.1:8765. No public access or timers enabled."

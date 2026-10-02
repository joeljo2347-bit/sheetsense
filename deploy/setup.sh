#!/usr/bin/env bash
# Set up the public demo on a fresh Ubuntu 24.04 server (16 GB of memory or more).
#
#   scp -r deploy examples dist/sheetsense-*.whl root@SERVER:/root/
#   ssh root@SERVER 'bash /root/deploy/setup.sh demo.example.com'
#
# The site name gets an HTTPS certificate automatically. Without a domain, use the server's
# address with sslip.io, e.g. 203-0-113-7.sslip.io for 203.0.113.7.
set -euo pipefail

SITE=${1:?usage: setup.sh <site name, e.g. demo.example.com or 203-0-113-7.sslip.io>}
MODEL=${SHEETSENSE_MODEL:-gpt-oss:20b}
HERE=$(cd "$(dirname "$0")" && pwd)
WHEEL=$(ls "$HERE"/../sheetsense-*.whl 2>/dev/null | sort | tail -1)
[ -n "$WHEEL" ] || { echo "No sheetsense wheel next to deploy/ (build it with: python3 -m build --wheel)"; exit 1; }

echo "== packages"
apt-get update -qq
apt-get install -y -qq python3-venv caddy ufw curl >/dev/null

echo "== firewall: ssh and web only"
ufw allow OpenSSH >/dev/null
ufw allow 80,443/tcp >/dev/null
ufw --force enable >/dev/null

echo "== model runtime (listens on this machine only)"
command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/demo.conf <<EOF
[Service]
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_KEEP_ALIVE=24h
Environment=OLLAMA_NUM_PARALLEL=1
EOF
systemctl daemon-reload
systemctl restart ollama
sleep 3
ollama pull "$MODEL"

echo "== app"
id sheetsense >/dev/null 2>&1 || useradd --system --home /opt/sheetsense --shell /usr/sbin/nologin sheetsense
mkdir -p /opt/sheetsense/examples
python3 -m venv /opt/sheetsense/venv
/opt/sheetsense/venv/bin/pip install -q --upgrade pip
/opt/sheetsense/venv/bin/pip install -q "$WHEEL[web]"
cp "$HERE"/../examples/* /opt/sheetsense/examples/
chown -R root:root /opt/sheetsense

cat > /etc/systemd/system/sheetsense.service <<EOF
[Unit]
Description=sheetsense demo
After=network-online.target ollama.service
Wants=ollama.service

[Service]
User=sheetsense
Environment=SHEETSENSE_MODEL=$MODEL
Environment=SHEETSENSE_EXAMPLES=/opt/sheetsense/examples
ExecStart=/opt/sheetsense/venv/bin/uvicorn sheetsense.web:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
MemoryMax=1G

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/caddy/Caddyfile <<EOF
$SITE {
    encode gzip
    request_body {
        max_size 8MB
    }
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy no-referrer
        X-Frame-Options DENY
        -Server
    }
    reverse_proxy 127.0.0.1:8000
}
EOF

systemctl daemon-reload
systemctl enable --now sheetsense >/dev/null
systemctl reload caddy || systemctl restart caddy

echo "== warming the model"
curl -s http://127.0.0.1:11434/api/generate -d "{\"model\":\"$MODEL\",\"prompt\":\"hi\",\"stream\":false}" >/dev/null || true
sleep 2
curl -fsS http://127.0.0.1:8000/healthz && echo
echo "Done: https://$SITE"

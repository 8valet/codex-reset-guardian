#!/bin/sh
set -eu
guardian=$(command -v reset-guardian) || { echo 'reset-guardian is not in PATH. Install the package first.' >&2; exit 1; }
codex=$(command -v codex) || { echo 'codex is not in PATH. Install/sign in to Codex first.' >&2; exit 1; }
unit="$HOME/.config/systemd/user/codex-reset-guardian.service"
escape_systemd() {
  python3 - "$1" <<'PY'
import sys
print(sys.argv[1].replace('\\', '\\\\').replace('"', '\\"'))
PY
}
guardian_unit=$(escape_systemd "$guardian")
codex_unit=$(escape_systemd "$codex")
mkdir -p "$(dirname "$unit")"
cat > "$unit" <<UNIT
[Unit]
Description=Codex Reset Guardian
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
Environment="CODEX_RESET_GUARDIAN_CODEX=$codex_unit"
ExecStart="$guardian_unit" run
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now codex-reset-guardian.service
echo 'Installed user service. Guardian remains DISARMED until: reset-guardian arm'
echo 'For an always-on server, you may additionally enable user lingering with your system administrator.'

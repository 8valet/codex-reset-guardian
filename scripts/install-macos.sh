#!/bin/sh
set -eu
guardian=$(command -v reset-guardian) || { echo 'reset-guardian is not in PATH. Install the package first.' >&2; exit 1; }
codex=$(command -v codex) || { echo 'codex is not in PATH. Install/sign in to Codex first.' >&2; exit 1; }
escape_xml() {
  python3 - "$1" <<'PY'
import html, sys
print(html.escape(sys.argv[1], quote=True))
PY
}
guardian_xml=$(escape_xml "$guardian")
codex_xml=$(escape_xml "$codex")
log_path="$HOME/Library/Logs/codex-reset-guardian.log"
log_xml=$(escape_xml "$log_path")
plist="$HOME/Library/LaunchAgents/com.8valet.codex-reset-guardian.plist"
mkdir -p "$(dirname "$plist")"
cat > "$plist" <<EOF2
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.8valet.codex-reset-guardian</string>
<key>ProgramArguments</key><array><string>$guardian_xml</string><string>run</string></array>
<key>EnvironmentVariables</key><dict><key>CODEX_RESET_GUARDIAN_CODEX</key><string>$codex_xml</string></dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>$log_xml</string>
<key>StandardErrorPath</key><string>$log_xml</string>
</dict></plist>
EOF2
launchctl bootout "gui/$(id -u)" "$plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo 'Installed LaunchAgent. Guardian remains DISARMED until: reset-guardian arm'

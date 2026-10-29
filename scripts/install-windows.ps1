$ErrorActionPreference = 'Stop'
$cmd = Get-Command reset-guardian -ErrorAction Stop
$exe = $cmd.Source
$codex = (Get-Command codex -ErrorAction Stop).Source
$task = 'Codex Reset Guardian'
$escaped = $exe.Replace("'", "''")
$codexEscaped = $codex.Replace("'", "''")
$action = "powershell.exe -NoProfile -WindowStyle Hidden -Command `"`$env:CODEX_RESET_GUARDIAN_CODEX='$codexEscaped'; & '$escaped' run`""
schtasks.exe /Create /SC ONLOGON /TN $task /TR $action /RL LIMITED /F | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Failed to create scheduled task" }
Write-Host 'Installed per-user logon task. Guardian remains DISARMED until: reset-guardian arm'

# Starts the Insightex Ollama server (run by the Task Scheduler task "Insightex Ollama"; deployed copy: E:\FYP\start_ollama.ps1).
# Loopback only. Logs ollama serve output to E:\FYP\logs\ollama_serve.log and exits with its exit code.
$env:OLLAMA_MODELS = "E:\FYP\LLMs"
$env:OLLAMA_HOST = "127.0.0.1:11434"
$logDir = "E:\FYP\logs"
$log = Join-Path $logDir "ollama_serve.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
# Keep one previous log once the current one passes 50 MB.
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 50MB)) { Move-Item -Force $log "$log.1" }
Add-Content -Path $log -Value "=== $(Get-Date -Format o) start: ollama serve, OLLAMA_MODELS=$env:OLLAMA_MODELS, OLLAMA_HOST=$env:OLLAMA_HOST"
Write-Host "Starting Ollama serve with OLLAMA_MODELS=$env:OLLAMA_MODELS, OLLAMA_HOST=$env:OLLAMA_HOST (log: $log)..."
# cmd /c so that stdout and stderr go to the file as plain text and $LASTEXITCODE is ollama's exit code.
cmd /c "ollama serve >> `"$log`" 2>&1"
$code = $LASTEXITCODE
Add-Content -Path $log -Value "=== $(Get-Date -Format o) ollama serve exited with code $code"
exit $code

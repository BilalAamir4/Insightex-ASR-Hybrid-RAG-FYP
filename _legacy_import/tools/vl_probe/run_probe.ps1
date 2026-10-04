param(
    [Parameter(Mandatory=$true)]
    [string]$RunLabel,

    [string]$ExtraEnv = ""
)

$outFile = "E:\FYP\data\frames\out\vram_run$RunLabel.csv"
if (Test-Path $outFile) { Remove-Item -Force $outFile }

Write-Host "Checking baseline GPU memory before Run $RunLabel..."
$maxWaitSeconds = 120
$pollIntervalSeconds = 5
$elapsed = 0
$ready = $false

while ($elapsed -lt $maxWaitSeconds) {
    $vramStr = (nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits).Trim()
    $vram = [int]$vramStr
    Write-Host "Current GPU memory: $vram MiB (waiting for < 800 MiB, elapsed: $elapsed s)"
    if ($vram -lt 800) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds $pollIntervalSeconds
    $elapsed += $pollIntervalSeconds
}

if (-not $ready) {
    Write-Host "ERROR: GPU memory did not drop below 800 MiB within 120 seconds!"
    Write-Host "Listing processes holding GPU:"
    nvidia-smi
    exit 1
}

Write-Host "GPU memory is ready ($vram MiB). Starting background sampler -> $outFile"
$sampler = Start-Process -FilePath "nvidia-smi" -ArgumentList "--query-gpu=memory.used --format=csv,noheader,nounits -lms 500" -RedirectStandardOutput $outFile -PassThru -NoNewWindow

Start-Sleep -Seconds 2

try {
    Write-Host "Launching probe in WSL with timeout 600..."
    $cmd = "source ~/envs/paddleocr-vl/bin/activate && $ExtraEnv timeout 600 python /mnt/e/FYP/tools/vl_probe/probe.py"
    Write-Host "WSL Command: $cmd"
    wsl -d Ubuntu-24.04 -- bash -lc "$cmd"
}
finally {
    Start-Sleep -Seconds 2
    Write-Host "Stopping nvidia-smi sampler (PID: $($sampler.Id))..."
    Stop-Process -Id $sampler.Id -Force -ErrorAction SilentlyContinue
    Write-Host "Sampler stopped."
}

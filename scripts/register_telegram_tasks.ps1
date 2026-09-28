# Registers two Windows Task Scheduler jobs that run notify.py:
#   "Weather Telegram - morning"  -> today's forecast    (default 07:00)
#   "Weather Telegram - evening"  -> tomorrow's forecast (default 20:00)
#
# Usage (from the weather_dashboard folder):
#   .\scripts\register_telegram_tasks.ps1
#   .\scripts\register_telegram_tasks.ps1 -MorningTime 07:30 -EveningTime 21:00
#   .\scripts\register_telegram_tasks.ps1 -Unregister
#
# Tasks run as the current user, only while logged on. If the computer was asleep
# or off at the scheduled time, the task runs as soon as possible afterwards.

param(
    [string]$MorningTime = "07:00",
    [string]$EveningTime = "20:00",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectDir ".venv\Scripts\python.exe"
$script = Join-Path $projectDir "notify.py"

$jobs = @(
    @{ Name = "Weather Telegram - morning"; Mode = "morning"; Time = $MorningTime },
    @{ Name = "Weather Telegram - evening"; Mode = "evening"; Time = $EveningTime }
)

if ($Unregister) {
    foreach ($job in $jobs) {
        Unregister-ScheduledTask -TaskName $job.Name -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Removed: $($job.Name)"
    }
    return
}

if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $python. Create it first (see README)."
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

foreach ($job in $jobs) {
    $action = New-ScheduledTaskAction -Execute $python -Argument "`"$script`" $($job.Mode)" `
        -WorkingDirectory $projectDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $job.Time
    Register-ScheduledTask -TaskName $job.Name -Action $action -Trigger $trigger -Settings $settings `
        -Description "Sends the $($job.Mode) weather forecast to Telegram (notify.py)" -Force | Out-Null
    Write-Host "Registered: $($job.Name) at $($job.Time) daily"
}

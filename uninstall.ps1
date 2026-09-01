<#
.SYNOPSIS
    Jarvis - Windows uninstaller.

.DESCRIPTION
    A copy of this script is installed alongside Jarvis, so the usual way to
    run it is from the install itself:

        & "$env:LOCALAPPDATA\Jarvis\uninstall.ps1"

    Only install.ps1 is published anywhere. If the install is too broken to
    run its own copy, fetch this one from the repo instead - fill in the same
    RAW_INSTALL_URL host install.ps1 came from:

        irm <RAW_UNINSTALL_URL> | iex

    Stops Jarvis if it's running, removes the shortcut and the PATH entry,
    and deletes the install directory - the private Python, the checkout,
    jarvis_config.json, logs, everything under it.

    This does NOT touch FreeClaw, or anything Jarvis put there: the "Jarvis"
    FreeClaw user, its memory (context.md), or the registered MCP server
    entry. Removing those is a separate, deliberate choice - see the summary
    this script prints at the end for how, if you want that too.

.PARAMETER InstallDir
    Where Jarvis lives. Defaults to the directory this script is in when
    that is an install, and to %LOCALAPPDATA%\Jarvis otherwise.

.PARAMETER Yes
    Do not ask for confirmation.

.NOTES
    Piped through `iex` there is nowhere to put parameters, so each one also
    reads an environment variable: JARVIS_DIR, JARVIS_YES.
#>
[CmdletBinding()]
param(
    [string]$InstallDir,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

function Env-Or($value, $name) {
    if ($value) { return $value }
    $v = [Environment]::GetEnvironmentVariable($name)
    if ($v) { return $v }
    return $null
}
function Env-Flag($switch, $name) {
    if ($switch) { return $true }
    $v = [Environment]::GetEnvironmentVariable($name)
    return [bool]($v -and $v -ne "0" -and $v -ne "false")
}

$InstallDir = Env-Or $InstallDir "JARVIS_DIR"
$Yes        = Env-Flag $Yes "JARVIS_YES"

if (-not $InstallDir) {
    # A copy of this script ships inside every install, so if it is sitting
    # in one, that is the install to remove - whatever directory it happens
    # to be in. $PSScriptRoot is empty when the script is piped through
    # `iex`, which is what falls through to the default location.
    #
    # Guessing from the app files instead of this marker does not work: after
    # an uninstall they are gone, which is precisely the moment someone might
    # run this a second time.
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot ".jarvis-install"))) {
        $InstallDir = $PSScriptRoot
    } else {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Jarvis"
    }
}

function Step($text) { Write-Host ""; Write-Host "  $text" -ForegroundColor Cyan }
function Info($text) { Write-Host "     $text" -ForegroundColor DarkGray }
function Ok($text)   { Write-Host "     $text" -ForegroundColor Green }
function Die($text)  { Write-Host ""; Write-Host "  x $text" -ForegroundColor Red; Write-Host ""; exit 1 }

Write-Host ""
Write-Host "  Jarvis - uninstall" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $InstallDir)) { Die "Nothing installed at $InstallDir." }

Info "install:  $InstallDir"
Info "removes:  the private Python, the app, jarvis_config.json, logs - everything under it"
Info "leaves:   FreeClaw untouched - its `"Jarvis`" user and memory are not deleted"

if (-not $Yes) {
    Write-Host ""
    $answer = Read-Host "  Continue? [y/N]"
    if ($answer -ne "y" -and $answer -ne "Y") { Write-Host "  Cancelled."; Write-Host ""; exit 0 }
}

# -- stop it, if it's running -----------------------------------
Step "Stopping Jarvis, if it's running"
$stopped = 0
Get-Process -Name "python", "pythonw" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; $stopped++ }
if ($stopped -gt 0) { Ok "stopped" } else { Info "wasn't running" }

# -- shortcut / PATH ----------------------------------------------
Step "Removing shortcut and PATH entry"

# Only ours. A shortcut called Jarvis.lnk could in principle belong to a
# different install pointed somewhere else - checked against $InstallDir
# before it goes, rather than removed on the strength of its name alone.
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Jarvis.lnk"
if (Test-Path $lnk) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $target = $shell.CreateShortcut($lnk).TargetPath
    } catch { $target = $null }
    if ($target -and $target.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item $lnk -Force
        Ok "Start Menu shortcut"
    } else {
        Info "left the Start Menu shortcut alone - it points at another install"
    }
}

# Our one entry, matched whole, and only rewritten if it is actually there.
# Anything else here would be editing the user's PATH on their behalf.
$binDir = (Join-Path $InstallDir "bin").TrimEnd('\').ToLower()
$key = "HKCU:\Environment"
$current = (Get-ItemProperty -Path $key -Name Path -ErrorAction SilentlyContinue).Path
if ($current) {
    $kept = @()
    $found = $false
    foreach ($entry in ($current -split ';')) {
        if ($entry.Trim() -eq "") { continue }
        if ($entry.Trim().TrimEnd('\').ToLower() -eq $binDir) { $found = $true; continue }
        $kept += $entry
    }
    if ($found) {
        Set-ItemProperty -Path $key -Name Path -Value ($kept -join ';') -Type ExpandString
        Ok "PATH entry"
    }
}

# -- files ----------------------------------------------------
Step "Removing files"
# Everything except this script first, so a genuine problem (a file still
# open, a permissions issue) is reported rather than hidden behind the
# self-delete below. uninstall.ps1 is, on a normal run, the file this very
# process is executing - deleting that mid-run would abort the script.
foreach ($item in Get-ChildItem $InstallDir -Force) {
    if ($item.Name -eq "uninstall.ps1") { continue }
    Remove-Item $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
$left = @(Get-ChildItem $InstallDir -Force | Where-Object { $_.Name -ne "uninstall.ps1" })
if ($left.Count) {
    Die ("Couldn't fully delete $InstallDir - " +
         "$($left.Count) item(s) left, something still has a file open. " +
         "Try again after signing out.")
}
# A running script cannot delete itself. Hand the last step to a detached
# cmd that waits for this process to exit first.
$cmd = 'timeout /t 2 /nobreak >nul & rmdir /s /q "' + $InstallDir + '"'
Start-Process cmd.exe -ArgumentList '/c', $cmd -WindowStyle Hidden | Out-Null
Ok "everything removed"

Write-Host ""
Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Jarvis has been uninstalled." -ForegroundColor Green
Write-Host ""
Write-Host "  FreeClaw wasn't touched. If you want the `"Jarvis`" user and its" -ForegroundColor DarkGray
Write-Host "  memory gone too, open FreeClaw and delete the user from there," -ForegroundColor DarkGray
Write-Host "  and remove the `"jarvis`" entry under Settings -> MCP Servers." -ForegroundColor DarkGray
Write-Host ""

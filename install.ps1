<#
.SYNOPSIS
    Jarvis - Windows installer.

.DESCRIPTION
    irm <RAW_INSTALL_URL> | iex

    Clones Jarvis into %LOCALAPPDATA%\Jarvis, fetches a private copy of
    Python for it, installs the dependencies, connects it to a local FreeClaw
    install, and starts it. No administrator rights at any point.

    Jarvis is a shell around FreeClaw - it needs FreeClaw installed on this
    same machine to think with at all, and its own MCP server (screenshots,
    file access, drawing on the display) only works run alongside it. If
    FreeClaw isn't found, this script says so and stops before installing
    anything that couldn't do anything useful yet:

        irm https://freeclaw.eedeb.dev/install.ps1 | iex

    Nothing is hosted anywhere except this script: the source comes from the
    GitHub repo and the interpreter comes from python.org, so a release never
    has to be cut or an artifact uploaded for an install to work.

    Python is a *private* copy under the install directory - the embeddable
    distribution. It is not added to PATH and does not touch any Python you
    already have.

    Re-running it is the update path: code is refreshed from the repo, the
    FreeClaw connection is re-run (safe - setup.py is idempotent), and your
    settings (jarvis_config.json, outside the checkout) are never touched.

.PARAMETER InstallDir
    Where to install. Default: %LOCALAPPDATA%\Jarvis.

.PARAMETER Branch
    Branch to track. Default: main.

.PARAMETER NoStart
    Install but do not launch Jarvis afterwards.

.PARAMETER NoShortcut
    Skip the Start Menu shortcut.

.PARAMETER NoPath
    Do not add the `jarvis` / `jarvis-setup` commands to PATH.

.NOTES
    Piped through `iex` there is nowhere to put parameters, so each one also
    reads an environment variable: JARVIS_DIR, JARVIS_BRANCH,
    JARVIS_NO_START, JARVIS_NO_SHORTCUT, JARVIS_NO_PATH.
#>
[CmdletBinding()]
param(
    [string]$InstallDir,
    [string]$Branch,
    [switch]$NoStart,
    [switch]$NoShortcut,
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"

# Invoke-WebRequest draws a progress bar by writing to the console on every
# chunk, which on Windows PowerShell makes a large download several times
# slower than it needs to be.
$ProgressPreference = "SilentlyContinue"

# TODO before publishing: point this at the real repository.
$RepoUrl = "https://github.com/OWNER/REPO"
$PythonVersion = "3.12.8"

# -- parameters, or the environment when piped through iex ----
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
$Branch     = Env-Or $Branch     "JARVIS_BRANCH"
$NoStart    = Env-Flag $NoStart    "JARVIS_NO_START"
$NoShortcut = Env-Flag $NoShortcut "JARVIS_NO_SHORTCUT"
$NoPath     = Env-Flag $NoPath     "JARVIS_NO_PATH"

if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA "Jarvis" }
if (-not $Branch)     { $Branch = "main" }

$FreeClawDir = Join-Path $env:LOCALAPPDATA "FreeClaw"

# -- output ---------------------------------------------------
function Step($text) { Write-Host ""; Write-Host "  $text" -ForegroundColor Cyan }
function Info($text) { Write-Host "     $text" -ForegroundColor DarkGray }
function Ok($text)   { Write-Host "     $text" -ForegroundColor Green }
function Warn($text) { Write-Host "     ! $text" -ForegroundColor Yellow }
function Die($text)  { Write-Host ""; Write-Host "  x $text" -ForegroundColor Red; Write-Host ""; exit 1 }

# Every external command goes through this, for one specific reason: Windows
# PowerShell turns a native command's stderr into ErrorRecords when it is
# redirected, and with $ErrorActionPreference = 'Stop' the first line git
# writes to stderr - "From https://github.com/..." on a perfectly *successful*
# fetch - aborts the whole script. Relaxing the preference for the duration of
# the call and then checking the real exit code is what makes that survivable.
# Output is left in $script:Out for the callers that want it.
$script:Out = @()
function Native($exe, [string[]]$arguments) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $script:Out = @(& $exe @arguments 2>&1 | ForEach-Object { "$_" })
    } finally {
        $ErrorActionPreference = $prev
    }
    return $LASTEXITCODE
}

Write-Host ""
Write-Host "  Jarvis" -ForegroundColor Green -NoNewline
Write-Host " - a voice assistant, thinking with FreeClaw"
Write-Host ""

# -- 1. preflight ---------------------------------------------
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Die "PowerShell 5 or newer is required (found $($PSVersionTable.PSVersion))."
}
if (-not [Environment]::Is64BitOperatingSystem) {
    Die "Jarvis needs 64-bit Windows."
}
if ([Environment]::OSVersion.Version.Major -lt 10) {
    Die "Windows 10 or newer is required."
}
# Windows PowerShell defaults to SSL3/TLS1.0, which github.com and python.org
# both refuse.
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) {
    Die ("Git is required and isn't installed.`n" +
         "     Install it with:  winget install --id Git.Git -e`n" +
         "     or from https://git-scm.com/download/win , then run this again.")
}

# -- 2. FreeClaw ------------------------------------------------
# Checked first, before anything is installed: a Jarvis with nothing to think
# with cannot do anything useful yet, and there is no reason to leave a
# half-set-up app on disk when the fix is "install FreeClaw, run this again".
Step "Looking for FreeClaw"
$FreeClawFound = Test-Path (Join-Path $FreeClawDir "Flask\static")
if (-not $FreeClawFound) {
    Write-Host ""
    Write-Host "  x FreeClaw isn't installed." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Jarvis needs FreeClaw right here - its MCP server runs as a child" -ForegroundColor DarkGray
    Write-Host "  process of FreeClaw, and can only screenshot this screen or draw on" -ForegroundColor DarkGray
    Write-Host "  this UI if it's running beside them. Install it, then run this again:" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "      irm https://freeclaw.eedeb.dev/install.ps1 | iex" -ForegroundColor Green
    Write-Host ""
    exit 1
}
Ok "found at $FreeClawDir"

$FreeClawRunning = $false
try {
    $r = Invoke-WebRequest "http://127.0.0.1:6767/login" -UseBasicParsing -TimeoutSec 2
    $FreeClawRunning = ($r.StatusCode -eq 200)
} catch { }
if ($FreeClawRunning) {
    Ok "and it's running"
} else {
    Warn "installed, but not answering on http://127.0.0.1:6767 right now"
    Info "start it from the tray (or run `"freeclaw`" in a terminal) before connecting Jarvis"
}

$IsUpgrade = Test-Path (Join-Path $InstallDir ".git")

# -- 3. source ----------------------------------------------------
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Push-Location $InstallDir
try {
    if ($IsUpgrade) {
        Step "Updating from $RepoUrl"
        if ((Native $git @("fetch", "--depth", "1", "origin", $Branch)) -ne 0) {
            Die "git fetch failed - no network, or the repo moved."
        }
        if ((Native $git @("checkout", "-f", "-B", $Branch, "origin/$Branch")) -ne 0) {
            Die "git checkout failed.`n     $($script:Out -join "`n     ")"
        }
        Ok "source updated"
    } else {
        Step "Cloning $RepoUrl"
        # init + fetch rather than `git clone`, because the directory may
        # already exist: someone made the folder first, or a previous
        # install left files behind. clone refuses a non-empty target; this
        # does not.
        if (-not (Test-Path (Join-Path $InstallDir ".git"))) {
            Native $git @("init", "-q") | Out-Null
            Native $git @("remote", "add", "origin", $RepoUrl) | Out-Null
        }
        if ((Native $git @("fetch", "--depth", "1", "origin", $Branch)) -ne 0) {
            Die "Couldn't fetch $RepoUrl - check your network.`n     $($script:Out -join "`n     ")"
        }
        if ((Native $git @("checkout", "-f", "-B", $Branch, "origin/$Branch")) -ne 0) {
            Die "git checkout failed.`n     $($script:Out -join "`n     ")"
        }
        Ok "source cloned"
    }
} finally {
    Pop-Location
}

# -- 4. python --------------------------------------------------
# The embeddable distribution: a private interpreter under the install
# directory. Skipped when it is already there, so re-running to update is
# quick.
$PyDir = Join-Path $InstallDir "python"
$PyExe = Join-Path $PyDir "python.exe"
if (-not (Test-Path $PyExe)) {
    Step "Fetching Python $PythonVersion"
    $zipName = "python-$PythonVersion-embed-amd64.zip"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("jarvis-py-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    $pyZip = Join-Path $tmp $zipName
    try {
        Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/$zipName" `
            -OutFile $pyZip -UseBasicParsing
    } catch {
        Die "Couldn't download Python: $($_.Exception.Message)"
    }
    New-Item -ItemType Directory -Path $PyDir -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($pyZip, $PyDir)
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

    # The embeddable build ships a ._pth that REPLACES normal path
    # computation: no site-packages, and no entry for the app. Two edits fix
    # both.
    $pth = Get-ChildItem -Path $PyDir -Filter "python*._pth" | Select-Object -First 1
    if (-not $pth) { Die "The Python download is missing its ._pth file." }
    $lines = Get-Content $pth.FullName
    $lines = $lines | ForEach-Object {
        if ($_ -match '^\s*#\s*import\s+site\s*$') { "import site" } else { $_ }
    }
    if ($lines -notcontains "import site") { $lines += "import site" }
    # Paths in a ._pth resolve relative to the file, and the interpreter
    # lives one level down in python\, so "..\src" is where main.py's own
    # imports (jarvis_config, listen, ...) actually are.
    if ($lines -notcontains "..\src") { $lines += "..\src" }
    Set-Content -Path $pth.FullName -Value $lines -Encoding ASCII

    $getPip = Join-Path $PyDir "get-pip.py"
    Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing
    Native $PyExe @($getPip, "--no-warn-script-location", "--no-cache-dir") | Out-Null
    Remove-Item $getPip -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path (Join-Path $PyDir "Lib\site-packages\pip"))) {
        Die "Couldn't bootstrap pip into the bundled Python."
    }
    Ok "python $PythonVersion installed privately"
} else {
    Info "using the Python already in $PyDir"
}

# -- 5. dependencies --------------------------------------------
Step "Installing dependencies"
Info "this is the slow part on a first install - faster-whisper and its"
Info "speech models are a real download"
$code = Native $PyExe @("-m", "pip", "install", "--no-cache-dir",
                        "--no-warn-script-location", "--disable-pip-version-check",
                        "-r", (Join-Path $InstallDir "requirements.txt"))
if ($code -ne 0) {
    $script:Out | Where-Object { $_ -match 'ERROR|error:' } | Select-Object -Last 5 |
        ForEach-Object { Info $_ }
    Die "pip install failed - see the errors above."
}
Ok "dependencies installed"

# -- 6. the jarvis commands ---------------------------------------
# Their own directory, because that is what goes on PATH - everything else
# under the install root would come with it, and putting python.exe on a
# user's PATH is not something an app should do behind their back.
$binDir = Join-Path $InstallDir "bin"
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
foreach ($shim in @("jarvis.cmd", "jarvis-setup.cmd")) {
    Copy-Item (Join-Path $InstallDir "windows\$shim") -Destination $binDir -Force
}

# -- 7. connect to FreeClaw ---------------------------------------
Step "Connecting to FreeClaw"
if ($FreeClawRunning) {
    $code = Native $PyExe @((Join-Path $InstallDir "src\setup.py"))
    $script:Out | ForEach-Object { Write-Host "     $_" }
    if ($code -ne 0) {
        Warn "setup didn't finish - run `"jarvis-setup`" after fixing the issue above"
    }
} else {
    Warn "FreeClaw isn't running, so this step is skipped"
    Info "once it's up, run `"jarvis-setup`" (or `"$InstallDir\bin\jarvis-setup.cmd`")"
}

# The marker uninstall.ps1 keys off. An install is a clone of the repo, so it
# looks exactly like a developer's checkout from the outside - this file is
# the only thing that tells them apart. Gitignored, so a checkout never has
# one.
Set-Content -LiteralPath (Join-Path $InstallDir ".jarvis-install") -Encoding ascii -Value @(
    "# Written by install.ps1. Its presence marks this directory as a Jarvis",
    "# install rather than a source checkout; uninstall.ps1 looks for it.",
    "installed=$(Get-Date -Format s)"
)

# -- 8. shortcut, PATH -------------------------------------------
$pythonw = Join-Path $PyDir "pythonw.exe"
$mainScript = Join-Path $InstallDir "src\main.py"
$icon = Join-Path $InstallDir "windows\jarvis.ico"

if (-not $NoShortcut) {
    $lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Jarvis.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $pythonw
    $s.Arguments = '"' + $mainScript + '"'
    $s.WorkingDirectory = Join-Path $InstallDir "src"
    $s.IconLocation = $icon
    $s.Description = "Jarvis"
    $s.Save()
    Ok "Start Menu shortcut"
}

if (-not $NoPath) {
    # HKCU\Environment\Path is the user's own PATH and one careless write
    # stops every command on the machine resolving. So: read it unexpanded
    # (it routinely contains %USERPROFILE%), compare whole entries, and only
    # write when our bin directory is genuinely absent.
    $key = "HKCU:\Environment"
    $current = (Get-ItemProperty -Path $key -Name Path -ErrorAction SilentlyContinue).Path
    if ($null -eq $current) { $current = "" }
    $entries = $current -split ';' | Where-Object { $_.Trim() -ne "" }
    $normalised = $entries | ForEach-Object { $_.Trim().TrimEnd('\').ToLower() }
    if ($normalised -notcontains $binDir.TrimEnd('\').ToLower()) {
        Set-ItemProperty -Path $key -Name Path -Value ((@($entries) + $binDir) -join ';') `
                         -Type ExpandString
        Ok "added $binDir to PATH (open a new terminal to pick it up)"
    }
}

# -- 9. start ---------------------------------------------------
if ((-not $NoStart) -and $FreeClawRunning) {
    Step "Starting Jarvis"
    Start-Process -FilePath $pythonw -ArgumentList ('"' + $mainScript + '"') `
                  -WorkingDirectory (Join-Path $InstallDir "src")
    Ok "launched"
} elseif (-not $NoStart) {
    Info "not starting Jarvis yet - start FreeClaw first, then run `"jarvis`""
}

# -- done -------------------------------------------------------
Write-Host ""
Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
if ($IsUpgrade) {
    Write-Host "  Jarvis updated." -ForegroundColor Green
    Write-Host "  Your settings were left untouched." -ForegroundColor DarkGray
} else {
    Write-Host "  Jarvis is installed." -ForegroundColor Green
}
Write-Host ""
Write-Host "  Run         " -NoNewline -ForegroundColor DarkGray
Write-Host "jarvis"
Write-Host "  Reconnect   " -NoNewline -ForegroundColor DarkGray
Write-Host "jarvis-setup   (after editing the persona, or moving FreeClaw)"
Write-Host "  Update      " -NoNewline -ForegroundColor DarkGray
Write-Host "run this installer again"
Write-Host "  Uninstall   " -NoNewline -ForegroundColor DarkGray
Write-Host "& `"$InstallDir\uninstall.ps1`""
Write-Host ""
if (-not $FreeClawRunning) {
    Write-Host "  Start FreeClaw, then run " -NoNewline -ForegroundColor Yellow
    Write-Host "jarvis-setup" -NoNewline -ForegroundColor Green
    Write-Host " to finish connecting the two." -ForegroundColor Yellow
    Write-Host ""
}
Write-Host "  Say `"Hey Jarvis`" once it's open." -ForegroundColor DarkGray
Write-Host ""

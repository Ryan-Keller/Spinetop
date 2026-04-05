[CmdletBinding()]
param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "start"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptRoot "..\..")).Path
$UiRoot = Join-Path $RepoRoot "ui"
$LauncherManifestPath = Join-Path $ScriptRoot "manifest.json"
$StateRoot = $null
$LogRoot = $null
$BackendPidFile = $null
$FrontendPidFile = $null
$LanProxyPidFile = $null
$StateFile = $null
$BackendLog = $null
$FrontendLog = $null
$LanProxyLog = $null
$BackendUrl = $null
$FrontendUrl = $null
$DesktopApiUrl = $null
$DesktopUiUrl = $null
$LanApiUrl = $null
$LanIp = $null
$LanUiUrl = $null
$BackendPort = $null
$FrontendPort = $null
$WslDistro = $null
$FrontendBindAddress = $null

function Ensure-LauncherState {
    New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
}

function Convert-ToWslPath {
    param([Parameter(Mandatory = $true)][string]$WindowsPath)

    $path = $WindowsPath
    if (Test-Path -LiteralPath $WindowsPath) {
        $path = (Resolve-Path -LiteralPath $WindowsPath).Path
    }

    if ($path -match "^([A-Za-z]):\\(.*)$") {
        return "/mnt/$($matches[1].ToLowerInvariant())/$($matches[2] -replace '\\', '/')"
    }

    throw "Unsupported Windows path for WSL conversion: $WindowsPath"
}

function Get-LanIpAddress {
    $candidateRoutes = @()
    try {
        $candidateRoutes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop | Sort-Object RouteMetric, InterfaceMetric)
    } catch {
    }

    foreach ($route in $candidateRoutes) {
        try {
            $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.ifIndex -ErrorAction Stop |
                Where-Object {
                    $_.IPAddress -and
                    $_.IPAddress -ne "127.0.0.1" -and
                    $_.IPAddress -notlike "169.254*" -and
                    $_.PrefixOrigin -ne "WellKnown"
                } | Sort-Object SkipAsSource, PrefixOrigin)
            if ($addresses.Count -gt 0) {
                return [string]$addresses[0].IPAddress
            }
        } catch {
        }
    }

    try {
        $fallback = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -and
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } | Sort-Object InterfaceMetric, SkipAsSource | Select-Object -First 1
        if ($fallback) {
            return [string]$fallback.IPAddress
        }
    } catch {
    }

    return "127.0.0.1"
}

function Test-RunningAsAdministrator {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Ensure-LanFirewallRules {
    param(
        [Parameter(Mandatory = $true)][string]$ListenAddress,
        [Parameter(Mandatory = $true)][int[]]$Ports
    )

    if (-not (Test-RunningAsAdministrator)) {
        return [pscustomobject]@{
            is_admin = $false
            ensured = $false
            message = "Launcher is not elevated, so Windows firewall rules were not modified."
        }
    }

    $ruleResults = @()
    foreach ($port in $Ports) {
        $ruleName = "Spinetop Launcher LAN $port"
        $existing = $null
        try {
            $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction Stop | Select-Object -First 1
        } catch {
        }

        if ($existing) {
            try {
                $existing | Set-NetFirewallRule -Enabled True -Profile Private -Action Allow | Out-Null
                $ruleResults += [pscustomobject]@{
                    port = $port
                    rule_name = $ruleName
                    state = "enabled"
                }
            } catch {
                $ruleResults += [pscustomobject]@{
                    port = $port
                    rule_name = $ruleName
                    state = "error"
                    error = $_.Exception.Message
                }
            }
            continue
        }

        try {
            New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private -RemoteAddress LocalSubnet | Out-Null
            $ruleResults += [pscustomobject]@{
                port = $port
                rule_name = $ruleName
                state = "created"
            }
        } catch {
            $ruleResults += [pscustomobject]@{
                port = $port
                rule_name = $ruleName
                state = "error"
                error = $_.Exception.Message
            }
        }
    }

    return [pscustomobject]@{
        is_admin = $true
        ensured = $true
        listen_address = $ListenAddress
        rules = $ruleResults
    }
}

function Get-LanFirewallRuleState {
    param(
        [Parameter(Mandatory = $true)][int[]]$Ports
    )

    $ruleResults = @()
    foreach ($port in $Ports) {
        $ruleName = "Spinetop Launcher LAN $port"
        $rule = $null
        try {
            $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction Stop | Select-Object -First 1
        } catch {
        }

        if ($rule) {
            $ruleResults += [pscustomobject]@{
                port = $port
                rule_name = $ruleName
                state = if ($rule.Enabled) { "present" } else { "disabled" }
            }
        } else {
            $ruleResults += [pscustomobject]@{
                port = $port
                rule_name = $ruleName
                state = "missing"
            }
        }
    }

    $ready = -not ($ruleResults | Where-Object { $_.state -ne "present" })
    return [pscustomobject]@{
        ready = $ready
        rules = $ruleResults
    }
}

function Resolve-LauncherPath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$PathValue
    )

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return (Join-Path $BasePath $PathValue)
}

function Expand-LauncherCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Template,
        [Parameter(Mandatory = $true)][hashtable]$Values
    )

    $result = $Template
    foreach ($key in $Values.Keys) {
        $placeholder = '{' + $key + '}'
        $result = $result.Replace($placeholder, [string]$Values[$key])
    }

    if ($result -match '\{[A-Za-z][A-Za-z0-9_]*\}') {
        throw "Unresolved launcher command placeholder(s) in manifest command: $result"
    }

    return $result
}

function Initialize-LauncherConfig {
    . (Join-Path $ScriptRoot "validate-manifest.ps1")
    $manifest = Assert-LauncherManifest -ManifestPath $LauncherManifestPath

    $script:WslDistro = if ($env:SPINETOP_WSL_DISTRO) { $env:SPINETOP_WSL_DISTRO } else { [string]$manifest.wsl_distro }
    $script:BackendPort = [int]$manifest.ports.backend
    $script:FrontendPort = [int]$manifest.ports.frontend
    $script:FrontendBindAddress = "0.0.0.0"
    $script:StateRoot = Resolve-LauncherPath -BasePath $ScriptRoot -PathValue ([string]$manifest.paths.state_root)
    $script:LogRoot = Resolve-LauncherPath -BasePath $ScriptRoot -PathValue ([string]$manifest.paths.log_root)
    $script:BackendPidFile = Resolve-LauncherPath -BasePath $ScriptRoot -PathValue ([string]$manifest.paths.backend_pid_file)
    $script:FrontendPidFile = Resolve-LauncherPath -BasePath $ScriptRoot -PathValue ([string]$manifest.paths.frontend_pid_file)
    $script:LanProxyPidFile = Join-Path $StateRoot "frontend-lan-proxy.pid"
    $script:StateFile = Resolve-LauncherPath -BasePath $ScriptRoot -PathValue ([string]$manifest.paths.state_file)
    $script:BackendLog = Resolve-LauncherPath -BasePath $ScriptRoot -PathValue ([string]$manifest.paths.backend_log_file)
    $script:FrontendLog = Resolve-LauncherPath -BasePath $ScriptRoot -PathValue ([string]$manifest.paths.frontend_log_file)
    $script:LanProxyLog = Join-Path $LogRoot "frontend-lan-proxy.log"
    $script:DesktopApiUrl = [string]$manifest.urls.backend
    $script:DesktopUiUrl = [string]$manifest.urls.frontend
    $script:LanIp = Get-LanIpAddress
    $script:LanApiUrl = ("http://{0}:{1}/api/status" -f $script:LanIp, $script:BackendPort)
    $script:LanUiUrl = ("http://{0}:{1}/" -f $script:LanIp, $script:FrontendPort)
    $script:BackendUrl = $script:DesktopApiUrl
    $script:FrontendUrl = $script:DesktopUiUrl

    $script:BackendLaunchTemplate = [string]$manifest.launch_commands.backend
    $script:FrontendLaunchTemplate = [string]$manifest.launch_commands.frontend
}

function Test-TcpPort {
    param([Parameter(Mandatory = $true)][int]$Port)

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            if (-not $iar.AsyncWaitHandle.WaitOne(250)) {
                return $false
            }
            $client.EndConnect($iar)
            return $true
        } finally {
            $client.Close()
        }
    } catch {
        return $false
    }
}

function Write-PidFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Platform,
        [Parameter(Mandatory = $true)][int]$ProcessId
    )

    Set-Content -LiteralPath $Path -Value "$Platform|$ProcessId" -Encoding ASCII
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3 -ErrorAction Stop | Out-Null
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    return $false
}

function Read-PidFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{
            pid = $null
            platform = "unknown"
        }
    }

    try {
        $raw = (Get-Content -LiteralPath $Path -Raw).Trim()
        if ($raw -match "^(windows|wsl)\|(\d+)$") {
            return [pscustomobject]@{
                pid = [int]$matches[2]
                platform = $matches[1]
            }
        }
        if ($raw -match "^\d+$") {
            return [pscustomobject]@{
                pid = [int]$raw
                platform = "unknown"
            }
        }
    } catch {
        return [pscustomobject]@{
            pid = $null
            platform = "unknown"
        }
    }

    return [pscustomobject]@{
        pid = $null
        platform = "unknown"
    }
}

function Test-WindowsProcessAlive {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        return [bool](Get-Process -Id $ProcessId -ErrorAction Stop)
    } catch {
        return $false
    }
}

function Test-WslProcessAlive {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        & wsl.exe -d $WslDistro -- bash -lc "kill -0 $ProcessId" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-WslListeningProcessId {
    param([Parameter(Mandatory = $true)][int]$Port)

    try {
        $output = & wsl.exe -d $WslDistro -- bash -lc "ss -lptn | grep ':$Port' | head -n 1" 2>$null
        foreach ($line in @($output)) {
            $text = ([string]$line).Trim()
            if ($text -match "pid=(\d+)") {
                return [int]$matches[1]
            }
        }
    } catch {
    }

    return $null
}

function Get-ServiceState {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $pidRecord = Read-PidFile -Path $PidFile
    $processId = $pidRecord.pid
    $platform = $pidRecord.platform
    $pidAlive = $false
    if ($processId) {
        if ($platform -eq "windows") {
            $pidAlive = Test-WindowsProcessAlive -ProcessId $processId
        } elseif ($platform -eq "wsl") {
            $pidAlive = Test-WslProcessAlive -ProcessId $processId
        } else {
            $pidAlive = Test-WindowsProcessAlive -ProcessId $processId
            if (-not $pidAlive) {
                $pidAlive = Test-WslProcessAlive -ProcessId $processId
                if ($pidAlive) {
                    $platform = "wsl"
                } else {
                    $platform = "windows"
                }
            } else {
                $platform = "windows"
            }
        }
    }

    $portOpen = Test-TcpPort -Port $Port
    $state = "stopped"
    $detail = "not running"

    if ($processId -and $pidAlive) {
        $state = "running"
        $detail = "launcher-owned process alive"
    } elseif ($portOpen) {
        $state = "external"
        $detail = "port open without a live launcher pid"
    } elseif ($processId) {
        $state = "stale"
        $detail = "pid file is stale"
    }

    [pscustomobject]@{
        name = $Name
        pid_file = $PidFile
        pid = $processId
        platform = $platform
        port = $Port
        port_open = $portOpen
        state = $state
        detail = $detail
    }
}

function Try-Adopt-Backend {
    $state = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
    if ($state.state -ne "external") {
        return $state
    }

    $processId = Get-WslListeningProcessId -Port $BackendPort
    if ($processId) {
        Write-PidFile -Path $BackendPidFile -Platform "wsl" -ProcessId $processId
        return Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
    }

    try {
        $connection = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($connection) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction Stop
            $commandLine = [string]$process.CommandLine
            if ($commandLine -match "dashboard_api\.py") {
                Write-PidFile -Path $BackendPidFile -Platform "windows" -ProcessId ([int]$connection.OwningProcess)
                return Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
            }
        }
    } catch {
    }

    return $state
}

function Try-Adopt-Frontend {
    $state = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
    if ($state.state -ne "external") {
        return $state
    }

    $processId = Get-WslListeningProcessId -Port $FrontendPort
    if ($processId) {
        Write-PidFile -Path $FrontendPidFile -Platform "wsl" -ProcessId $processId
        return Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
    }

    try {
        $connection = Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction Stop | Select-Object -First 1
        if (-not $connection) {
            return $state
        }

        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction Stop
        $commandLine = [string]$process.CommandLine
        if ($commandLine -notmatch "vite" -and $commandLine -notmatch "npm run dev") {
            return $state
        }

        Write-PidFile -Path $FrontendPidFile -Platform "windows" -ProcessId ([int]$connection.OwningProcess)
        return Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
    } catch {
        return $state
    }
}

function Get-LanProxyState {
    $pidRecord = Read-PidFile -Path $LanProxyPidFile
    $processId = $pidRecord.pid
    $platform = $pidRecord.platform
    $pidAlive = $false
    if ($processId) {
        $pidAlive = Test-WindowsProcessAlive -ProcessId $processId
    }

    $portOpen = $false
    $listener = $null
    try {
        $listener = Get-NetTCPConnection -LocalAddress $LanIp -LocalPort $FrontendPort -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($listener) {
            $portOpen = $true
        }
    } catch {
    }

    $state = "stopped"
    $detail = "not running"

    if ($processId -and $pidAlive) {
        $state = "running"
        $detail = "launcher-owned process alive"
    } elseif ($portOpen) {
        $state = "external"
        $detail = "port open without a live launcher pid"
    } elseif ($processId) {
        $state = "stale"
        $detail = "pid file is stale"
    }

    [pscustomobject]@{
        name = "frontend-lan-proxy"
        pid_file = $LanProxyPidFile
        pid = $processId
        platform = $platform
        port = $FrontendPort
        port_open = $portOpen
        state = $state
        detail = $detail
        listen_address = $LanIp
        target_address = "127.0.0.1"
        target_port = $FrontendPort
    }
}

function Try-Adopt-LanProxy {
    $state = Get-LanProxyState
    if ($state.state -ne "external") {
        return $state
    }

    try {
        $listener = Get-NetTCPConnection -LocalAddress $LanIp -LocalPort $FrontendPort -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($listener) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction Stop
            $commandLine = [string]$process.CommandLine
            if ($commandLine -match "frontend_lan_proxy\.py") {
                Write-PidFile -Path $LanProxyPidFile -Platform "windows" -ProcessId ([int]$listener.OwningProcess)
                return Get-LanProxyState
            }
        }
    } catch {
    }

    return $state
}

function Write-StateFile {
    param(
        [Parameter(Mandatory = $true)]$BackendState,
        [Parameter(Mandatory = $true)]$FrontendState,
        $LanFirewallState,
        [Nullable[bool]]$LanUiReachable,
        [string]$Note = ""
    )

    $payload = [ordered]@{
        updated_at = (Get-Date).ToString("o")
        repo_root = $RepoRoot
        ui_root = $UiRoot
        wsl_distro = $WslDistro
        backend_url = $DesktopApiUrl
        frontend_url = $DesktopUiUrl
        lan_ip = $LanIp
        desktop_api_url = $DesktopApiUrl
        desktop_ui_url = $DesktopUiUrl
        lan_api_url = $LanApiUrl
        lan_ui_url = $LanUiUrl
        launcher = [ordered]@{
            frontend_api_base = "/api"
            frontend_bind_address = $FrontendBindAddress
            lan_ui_reachable = $LanUiReachable
            lan_firewall_state = $LanFirewallState
        }
        lan_proxy = Get-LanProxyState
        note = $Note
        backend = $BackendState
        frontend = $FrontendState
        logs = [ordered]@{
            backend = $BackendLog
            frontend = $FrontendLog
        }
    }

    ($payload | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Start-Backend {
    param([switch]$AlreadyChecked)

    if (-not $AlreadyChecked) {
        $state = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
        if ($state.state -eq "running") {
            return $state
        }
        if ($state.state -eq "external") {
            throw "Backend port $BackendPort is already in use by a non-launcher process. Refusing to start a duplicate."
        }
    }

    $repoWsl = Convert-ToWslPath -WindowsPath $RepoRoot
    $logWsl = Convert-ToWslPath -WindowsPath $BackendLog
    $cmd = Expand-LauncherCommand -Template $script:BackendLaunchTemplate -Values ([ordered]@{
            RepoWsl = $repoWsl
            BackendLogWsl = $logWsl
            BackendPort = $BackendPort
            WslDistro = $WslDistro
        })

    $output = & wsl.exe -d $WslDistro -- bash -lc $cmd 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Backend launch failed: $output"
    }

    $processId = $null
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline -and -not $processId) {
        $processId = Get-WslListeningProcessId -Port $BackendPort
        if (-not $processId) {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $processId) {
        throw "Backend launch did not create a live listener. Output: $output"
    }

    Write-PidFile -Path $BackendPidFile -Platform "wsl" -ProcessId $processId
    $state = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
    if ($state.state -ne "running") {
        throw "Backend launch did not create a live service. Output: $output"
    }

    return $state
}

function Start-Frontend {
    param([switch]$AlreadyChecked)

    if (-not $AlreadyChecked) {
        $state = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
        if ($state.state -eq "running") {
            return $state
        }
        if ($state.state -eq "external") {
            throw "Frontend port $FrontendPort is already in use by a non-launcher process. Refusing to start a duplicate."
        }
    }

    $uiWsl = Convert-ToWslPath -WindowsPath $UiRoot
    $logWsl = Convert-ToWslPath -WindowsPath $FrontendLog
    $cmd = Expand-LauncherCommand -Template $script:FrontendLaunchTemplate -Values ([ordered]@{
            UiWsl = $uiWsl
            FrontendLogWsl = $logWsl
            FrontendPort = $FrontendPort
            WslDistro = $WslDistro
        })

    $output = & wsl.exe -d $WslDistro -- bash -lc $cmd 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend launch failed: $output"
    }

    $processId = $null
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline -and -not $processId) {
        $processId = Get-WslListeningProcessId -Port $FrontendPort
        if (-not $processId) {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $processId) {
        throw "Frontend launch did not create a live listener. Output: $output"
    }

    Write-PidFile -Path $FrontendPidFile -Platform "wsl" -ProcessId $processId
    $state = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
    if ($state.state -ne "running") {
        throw "Frontend launch did not create a live service."
    }

    return $state
}

function Stop-Frontend {
    $state = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
    if ($state.state -eq "running" -and $state.pid) {
        if ($state.platform -eq "windows" -or ($state.platform -eq "unknown" -and (Test-WindowsProcessAlive -ProcessId $state.pid))) {
            & taskkill.exe /PID $state.pid /T /F | Out-Null
            Start-Sleep -Milliseconds 500
        } else {
            $listenerPid = Get-WslListeningProcessId -Port $FrontendPort
            if ($listenerPid) {
                $output = & wsl.exe -d $WslDistro -- bash -lc "kill $listenerPid; sleep 1; kill -9 $listenerPid >/dev/null 2>&1 || true" 2>&1
                if ($LASTEXITCODE -ne 0) {
                    throw "Frontend stop failed: $output"
                }
            }
        }
    }
    if (Test-Path -LiteralPath $FrontendPidFile) {
        Remove-Item -LiteralPath $FrontendPidFile -Force
    }
    return (Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort)
}

function Stop-Backend {
    $state = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
    if ($state.state -eq "running" -and $state.pid) {
        if ($state.platform -eq "windows" -and (Test-WindowsProcessAlive -ProcessId $state.pid)) {
            & taskkill.exe /PID $state.pid /T /F | Out-Null
            Start-Sleep -Milliseconds 500
        } else {
            $listenerPid = Get-WslListeningProcessId -Port $BackendPort
            if ($listenerPid) {
                $output = & wsl.exe -d $WslDistro -- bash -lc "kill $listenerPid; sleep 1; kill -9 $listenerPid >/dev/null 2>&1 || true" 2>&1
                if ($LASTEXITCODE -ne 0) {
                    throw "Backend stop failed: $output"
                }
            }
        }
    }
    if (Test-Path -LiteralPath $BackendPidFile) {
        Remove-Item -LiteralPath $BackendPidFile -Force
    }
    return (Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort)
}

function Start-LanProxy {
    param([switch]$AlreadyChecked)

    if (-not $AlreadyChecked) {
        $state = Get-LanProxyState
        if ($state.state -eq "running") {
            return $state
        }
        if ($state.state -eq "external") {
            $state = Try-Adopt-LanProxy
        }
        if ($state.state -eq "external") {
            throw "LAN proxy port $FrontendPort is already in use by a non-launcher process. Refusing to start a duplicate."
        }
    }

    $proxyScript = Join-Path $ScriptRoot "frontend_lan_proxy.py"
    if (-not (Test-Path -LiteralPath $proxyScript)) {
        throw "LAN proxy script not found: $proxyScript"
    }

    $pythonExe = $null
    try {
        $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
    } catch {
        $pythonExe = (Get-Command python -ErrorAction Stop).Source
    }

    $args = @(
        $proxyScript,
        "--listen-address", $LanIp,
        "--listen-port", $FrontendPort,
        "--target-address", "127.0.0.1",
        "--target-port", $FrontendPort
    )

    $process = Start-Process -FilePath $pythonExe -ArgumentList $args -WindowStyle Hidden -PassThru
    Write-PidFile -Path $LanProxyPidFile -Platform "windows" -ProcessId $process.Id

    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        $state = Get-LanProxyState
        if ($state.state -eq "running") {
            return $state
        }
        Start-Sleep -Milliseconds 250
    }

    throw "LAN proxy launch did not create a live listener."
}

function Stop-LanProxy {
    $state = Get-LanProxyState
    if ($state.state -eq "external") {
        $state = Try-Adopt-LanProxy
    }

    if ($state.state -eq "running" -and $state.pid) {
        if (Test-WindowsProcessAlive -ProcessId $state.pid) {
            & taskkill.exe /PID $state.pid /T /F | Out-Null
            Start-Sleep -Milliseconds 500
        }
    }

    if (Test-Path -LiteralPath $LanProxyPidFile) {
        Remove-Item -LiteralPath $LanProxyPidFile -Force
    }

    return (Get-LanProxyState)
}

function Format-ServiceLine {
    param($State)
    $pidText = if ($State.pid) { " pid=$($State.pid)" } else { "" }
    return "$($State.name): $($State.state)$pidText port=$($State.port) open=$($State.port_open) - $($State.detail)"
}

function Show-Status {
    $backend = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
    $frontend = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
    $lanProxy = Get-LanProxyState
    $firewallState = Get-LanFirewallRuleState -Ports @($FrontendPort, $BackendPort)
    $firewallMode = if ($firewallState.ready) { "ready" } else { "missing" }
    Write-Host (Format-ServiceLine $backend)
    Write-Host (Format-ServiceLine $frontend)
    Write-Host (Format-ServiceLine $lanProxy)
    Write-Host "desktop ui: $DesktopUiUrl"
    Write-Host "lan ui: $LanUiUrl"
    Write-Host "desktop api: $DesktopApiUrl"
    Write-Host "lan api: $LanApiUrl"
    Write-Host "lan ip: $LanIp"
    Write-Host "firewall: $firewallMode"
    Write-Host "state: $StateFile"
    Write-Host "logs: $LogRoot"
    if (Test-Path -LiteralPath $StateFile) {
        try {
            $stateJson = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
            if ($stateJson.updated_at) {
                Write-Host "last update: $($stateJson.updated_at)"
            }
            if ($stateJson.launcher -and $null -ne $stateJson.launcher.lan_ui_reachable) {
                Write-Host "lan probe: $($stateJson.launcher.lan_ui_reachable)"
            }
        } catch {
        }
    }
}

function Start-Launcher {
    Ensure-LauncherState

    $launchedBackend = $false
    $launchedFrontend = $false
    $launchedLanProxy = $false
    $note = ""
    $lanUiReachable = $null
    $lanFirewallState = $null

    try {
        $lanFirewallState = Ensure-LanFirewallRules -ListenAddress $LanIp -Ports @($FrontendPort, $BackendPort)
        if (-not $lanFirewallState.is_admin) {
            Write-Warning $lanFirewallState.message
        } else {
            $createdPorts = @($lanFirewallState.rules | Where-Object { $_.state -in @("created", "enabled") } | ForEach-Object { $_.port })
            if ($createdPorts.Count -gt 0) {
                Write-Host "lan firewall rules ready for ports: $($createdPorts -join ', ')"
            }
        }

        $backendState = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
        if ($backendState.state -eq "external") {
            $backendState = Try-Adopt-Backend
        }
        if ($backendState.state -eq "external") {
            throw "Backend port $BackendPort is already in use by a non-launcher process. Refusing to start a duplicate."
        }
        if ($backendState.state -eq "running") {
            Write-Host "backend already running pid=$($backendState.pid)"
        } else {
            $backendState = Start-Backend -AlreadyChecked
            $launchedBackend = $true
            Write-Host "backend started pid=$($backendState.pid)"
        }

        if (-not (Wait-ForHttp -Url $BackendUrl -TimeoutSeconds 60)) {
            throw "Backend did not become ready at $BackendUrl"
        }

        $frontendState = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
        if ($frontendState.state -eq "external") {
            $frontendState = Try-Adopt-Frontend
        }
        if ($frontendState.state -eq "external") {
            throw "Frontend port $FrontendPort is already in use by a non-launcher process. Refusing to start a duplicate."
        }
        if ($frontendState.state -eq "running") {
            Write-Host "frontend already running pid=$($frontendState.pid)"
        } else {
            $frontendState = Start-Frontend -AlreadyChecked
            $launchedFrontend = $true
            Write-Host "frontend started pid=$($frontendState.pid)"
        }

        if (-not (Wait-ForHttp -Url $FrontendUrl -TimeoutSeconds 60)) {
            throw "Frontend did not become ready at $FrontendUrl"
        }

        $lanProxyState = Get-LanProxyState
        if ($lanProxyState.state -eq "external") {
            $lanProxyState = Try-Adopt-LanProxy
        }
        if ($lanProxyState.state -eq "external") {
            throw "LAN proxy port $FrontendPort is already in use by a non-launcher process on $LanIp. Refusing to start a duplicate."
        } elseif ($lanProxyState.state -eq "running") {
            Write-Host "lan proxy already running pid=$($lanProxyState.pid)"
        } else {
            $lanProxyState = Start-LanProxy
            $launchedLanProxy = $true
            Write-Host "lan proxy started pid=$($lanProxyState.pid)"
        }

        $lanUiReachable = Wait-ForHttp -Url $LanUiUrl -TimeoutSeconds 10
        if (-not $lanUiReachable) {
            throw "Frontend is up locally, but the LAN URL did not respond from this host: $LanUiUrl"
        }

        Write-StateFile -BackendState $backendState -FrontendState $frontendState -LanFirewallState $lanFirewallState -LanUiReachable $lanUiReachable -Note "launcher started"

        try {
            Start-Process -FilePath $DesktopUiUrl | Out-Null
            Write-Host "opened browser at $DesktopUiUrl"
        } catch {
            Write-Warning "Services are up, but opening the browser failed: $($_.Exception.Message)"
        }

        Write-Host "desktop ui: $DesktopUiUrl"
        Write-Host "lan ui: $LanUiUrl"
        Write-Host "desktop api: $DesktopApiUrl"
        Write-Host "lan api: $LanApiUrl"

        Write-Host "launcher ready"
    } catch {
        if ($launchedLanProxy) {
            try { Stop-LanProxy | Out-Null } catch { }
        }
        if ($launchedFrontend) {
            try { Stop-Frontend | Out-Null } catch { }
        }
        if ($launchedBackend) {
            try { Stop-Backend | Out-Null } catch { }
        }
        Write-StateFile -BackendState (Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort) -FrontendState (Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort) -LanFirewallState $lanFirewallState -LanUiReachable $lanUiReachable -Note "launcher start failed"
        throw
    }
}

function Stop-Launcher {
    Ensure-LauncherState
    $lanProxyBefore = Get-LanProxyState
    $frontendBefore = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort
    $backendBefore = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort
    $lanProxyAfter = $null
    $frontendAfter = $null
    $backendAfter = $null

    if ($lanProxyBefore.state -eq "external") {
        Write-Warning "LAN proxy port $FrontendPort on $LanIp is in use by a non-launcher process; leaving it alone."
    } elseif ($lanProxyBefore.state -eq "running") {
        $lanProxyAfter = Stop-LanProxy
        Write-Host "lan proxy stopped"
    } else {
        Write-Host "lan proxy already stopped"
        $lanProxyAfter = $lanProxyBefore
    }

    if ($frontendBefore.state -eq "external") {
        Write-Warning "Frontend port $FrontendPort is in use by a non-launcher process; leaving it alone."
    } elseif ($frontendBefore.state -eq "running") {
        $frontendAfter = Stop-Frontend
        Write-Host "frontend stopped"
    } else {
        Write-Host "frontend already stopped"
        $frontendAfter = $frontendBefore
    }

    if ($backendBefore.state -eq "external") {
        Write-Warning "Backend port $BackendPort is in use by a non-launcher process; leaving it alone."
    } elseif ($backendBefore.state -eq "running") {
        $backendAfter = Stop-Backend
        Write-Host "backend stopped"
    } else {
        Write-Host "backend already stopped"
        $backendAfter = $backendBefore
    }

    if (-not $lanProxyAfter) { $lanProxyAfter = Get-LanProxyState }
    if (-not $frontendAfter) { $frontendAfter = Get-ServiceState -Name "frontend" -PidFile $FrontendPidFile -Port $FrontendPort }
    if (-not $backendAfter) { $backendAfter = Get-ServiceState -Name "backend" -PidFile $BackendPidFile -Port $BackendPort }
    Write-StateFile -BackendState $backendAfter -FrontendState $frontendAfter -Note "launcher stopped"
    Write-Host "launcher stopped"
}

Initialize-LauncherConfig
Ensure-LauncherState

try {
    switch ($Action) {
        "start" { Start-Launcher }
        "stop" { Stop-Launcher }
        "status" { Show-Status }
    }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}

function Assert-LauncherManifest {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath
    )

    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        throw "Launcher manifest not found: $ManifestPath"
    }

    try {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    } catch {
        throw "Launcher manifest is not valid JSON: $ManifestPath"
    }

    $requiredTopLevel = @("wsl_distro", "ports", "paths", "urls", "launch_commands")
    foreach ($name in $requiredTopLevel) {
        if (-not ($manifest.PSObject.Properties.Name -contains $name)) {
            throw "Launcher manifest is missing required top-level field '$name': $ManifestPath"
        }
    }

    foreach ($name in @("backend", "frontend")) {
        if (-not ($manifest.ports.PSObject.Properties.Name -contains $name)) {
            throw "Launcher manifest is missing required port '$name': $ManifestPath"
        }
        $portValue = [int]$manifest.ports.$name
        if ($portValue -lt 1 -or $portValue -gt 65535) {
            throw "Launcher manifest port '$name' is out of range: $portValue"
        }
    }

    if ([int]$manifest.ports.backend -eq [int]$manifest.ports.frontend) {
        throw "Launcher manifest ports must be different: backend and frontend are both $([int]$manifest.ports.backend)"
    }

    foreach ($pathName in @(
        "state_root",
        "log_root",
        "backend_pid_file",
        "frontend_pid_file",
        "state_file",
        "backend_log_file",
        "frontend_log_file"
    )) {
        if (-not ($manifest.paths.PSObject.Properties.Name -contains $pathName)) {
            throw "Launcher manifest is missing required path '$pathName': $ManifestPath"
        }
        if ([string]::IsNullOrWhiteSpace([string]$manifest.paths.$pathName)) {
            throw "Launcher manifest path '$pathName' cannot be empty: $ManifestPath"
        }
    }

    foreach ($urlName in @("backend", "frontend")) {
        if (-not ($manifest.urls.PSObject.Properties.Name -contains $urlName)) {
            throw "Launcher manifest is missing required URL '$urlName': $ManifestPath"
        }
        if ([string]::IsNullOrWhiteSpace([string]$manifest.urls.$urlName)) {
            throw "Launcher manifest URL '$urlName' cannot be empty: $ManifestPath"
        }
    }

    foreach ($commandName in @("backend", "frontend")) {
        if (-not ($manifest.launch_commands.PSObject.Properties.Name -contains $commandName)) {
            throw "Launcher manifest is missing required launch command '$commandName': $ManifestPath"
        }
        $commandValue = [string]$manifest.launch_commands.$commandName
        if ([string]::IsNullOrWhiteSpace($commandValue)) {
            throw "Launcher manifest launch command '$commandName' cannot be empty: $ManifestPath"
        }
    }

    $backendCommand = [string]$manifest.launch_commands.backend
    foreach ($token in @("{RepoWsl}", "{BackendLogWsl}")) {
        if ($backendCommand -notmatch [regex]::Escape($token)) {
            throw ("Launcher manifest backend launch command must contain {0}: {1}" -f $token, $ManifestPath)
        }
    }

    $frontendCommand = [string]$manifest.launch_commands.frontend
    foreach ($token in @("{UiWsl}", "{FrontendLogWsl}", "{FrontendPort}")) {
        if ($frontendCommand -notmatch [regex]::Escape($token)) {
            throw ("Launcher manifest frontend launch command must contain {0}: {1}" -f $token, $ManifestPath)
        }
    }

    return $manifest
}

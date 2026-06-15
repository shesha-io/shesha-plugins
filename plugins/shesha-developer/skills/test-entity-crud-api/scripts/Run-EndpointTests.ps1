# ============================================================================
# Shesha Project - Endpoint Test Runner
# ============================================================================
# This script ensures the backend server is running and executes endpoint tests
# Works with any Shesha-based project following standard conventions
# Usage: .\Run-EndpointTests.ps1 [-StartServer] [-UpdateEntities] [-FullErrors] [-Port <auto-detected>]
# ============================================================================

param(
    [switch]$StartServer,
    [switch]$UpdateEntities,
    [switch]$FullErrors,
    [int]$Port = 0,
    [string]$Username = "admin",
    [string]$Password = "123qwe",
    [int]$StartupTimeoutSeconds = 300,
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Determine repository root - use RepoRoot param or navigate up from script location
if ($RepoRoot -eq "") {
    $RepoRoot = (Get-Item $ScriptDir).Parent.Parent.Parent.Parent.FullName
}
$BackendDir = Join-Path $RepoRoot "backend"

# Auto-detect port from launchSettings.json if not specified
if ($Port -eq 0) {
    $launchSettings = Get-ChildItem -Path $BackendDir -Recurse -Filter "launchSettings.json" |
        Where-Object { $_.FullName -match "Web\.Host" } | Select-Object -First 1
    if ($launchSettings) {
        $json = Get-Content $launchSettings.FullName | ConvertFrom-Json

        # Ensure a "Project" profile exists - required for dotnet run
        if (-not $json.profiles.PSObject.Properties["Project"]) {
            Write-Host "  No 'Project' launch profile found - creating one..." -ForegroundColor Yellow

            # Derive port from iisSettings if available, otherwise default
            $defaultPort = 21021
            if ($json.iisSettings -and $json.iisSettings.iisExpress -and $json.iisSettings.iisExpress.applicationUrl) {
                if ($json.iisSettings.iisExpress.applicationUrl -match ":(\d+)") {
                    $defaultPort = [int]$Matches[1]
                }
            }

            $projectProfile = [PSCustomObject]@{
                commandName    = "Project"
                launchBrowser  = $false
                applicationUrl = "http://localhost:$defaultPort"
            }
            $json.profiles | Add-Member -NotePropertyName "Project" -NotePropertyValue $projectProfile
            $json | ConvertTo-Json -Depth 10 | Set-Content $launchSettings.FullName -Encoding UTF8
            Write-Host "  Created 'Project' profile (port $defaultPort) in $($launchSettings.FullName)" -ForegroundColor Green
        }

        # Read port from Project profile
        $projectProfile = $json.profiles.Project
        if ($projectProfile -and $projectProfile.applicationUrl) {
            $url = $projectProfile.applicationUrl -split ";" | Select-Object -First 1
            if ($url -match ":(\d+)") {
                $Port = [int]$Matches[1]
            }
        }
    }
    if ($Port -eq 0) { $Port = 21021 }
}
$BaseUrl = "http://localhost:$Port"
$ServerProcess = $null

# Project detection variables (populated by Find-ProjectFiles)
$script:SolutionFile = $null
$script:WebHostProject = $null
$script:DomainPath = $null
$script:DomainPaths = @()
$script:ProjectName = "Shesha Project"

# ============================================================================
# Helper Functions
# ============================================================================

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 76) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 76) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Status {
    param([string]$Text, [string]$Status, [string]$Color = "White")
    Write-Host "  $Text " -NoNewline
    Write-Host $Status -ForegroundColor $Color
}

function Find-ProjectFiles {
    <#
    .SYNOPSIS
    Auto-detect solution file, Web.Host project, and Domain folder
    #>

    # Find solution file
    $solutions = Get-ChildItem -Path $BackendDir -Filter "*.sln" -ErrorAction SilentlyContinue
    if ($solutions.Count -eq 0) {
        Write-Host "  ERROR: No solution file (*.sln) found in $BackendDir" -ForegroundColor Red
        return $false
    }
    $script:SolutionFile = $solutions[0].FullName

    # Extract project name from solution file (e.g., "LandBank.Crm" from "LandBank.Crm.sln")
    $script:ProjectName = [System.IO.Path]::GetFileNameWithoutExtension($solutions[0].Name)

    # Find Web.Host project - look for *.Web.Host.csproj
    $webHostProjects = Get-ChildItem -Path $BackendDir -Filter "*.Web.Host.csproj" -Recurse -ErrorAction SilentlyContinue
    if ($webHostProjects.Count -eq 0) {
        Write-Host "  ERROR: No Web.Host project (*.Web.Host.csproj) found in $BackendDir" -ForegroundColor Red
        return $false
    }
    $script:WebHostProject = $webHostProjects[0].FullName

    # Find ALL Domain folders - look for *.Domain project with a Domain subfolder
    $script:DomainPaths = @()
    $domainProjects = Get-ChildItem -Path $BackendDir -Filter "*.Domain.csproj" -Recurse -ErrorAction SilentlyContinue
    foreach ($proj in $domainProjects) {
        $domainFolder = Join-Path $proj.DirectoryName "Domain"
        if (Test-Path $domainFolder) {
            $script:DomainPaths += $domainFolder
        }
    }

    # Set DomainPath to first found for backwards compat
    if ($script:DomainPaths.Count -gt 0) {
        $script:DomainPath = $script:DomainPaths[0]
    }

    if ($script:DomainPaths.Count -eq 0) {
        # Fallback: look for any folder named "Domain" under src
        $srcPath = Join-Path $BackendDir "src"
        if (Test-Path $srcPath) {
            $domainFolders = Get-ChildItem -Path $srcPath -Directory -Recurse -Filter "Domain" -ErrorAction SilentlyContinue |
                Where-Object { $_.Parent.Name -match '\.Domain$' }
            foreach ($df in $domainFolders) {
                $script:DomainPaths += $df.FullName
            }
            if ($script:DomainPaths.Count -gt 0) {
                $script:DomainPath = $script:DomainPaths[0]
            }
        }
    }

    if ($script:DomainPaths.Count -eq 0) {
        Write-Host "  WARNING: No Domain folder found. Entity scanning will be skipped." -ForegroundColor Yellow
    }

    return $true
}

function Test-ServerRunning {
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/api/services/app/Session/GetCurrentLoginInformations" `
            -Method Get -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
        return $true
    }
    catch {
        return $false
    }
}

function Wait-ForServer {
    param([int]$TimeoutSeconds = 120)

    $elapsed = 0
    $spinChars = @('|', '/', '-', '\')
    $spinIndex = 0

    Write-Host "  Waiting for server to start " -NoNewline

    while ($elapsed -lt $TimeoutSeconds) {
        if (Test-ServerRunning) {
            Write-Host "`r  Server is ready!                    " -ForegroundColor Green
            return $true
        }

        Write-Host "`r  Waiting for server to start $($spinChars[$spinIndex]) ($elapsed s)" -NoNewline
        $spinIndex = ($spinIndex + 1) % 4
        Start-Sleep -Seconds 2
        $elapsed += 2
    }

    Write-Host "`r  Server startup timed out after $TimeoutSeconds seconds" -ForegroundColor Red
    return $false
}

function Build-Backend {
    Write-Host "  Building backend solution..." -ForegroundColor Yellow

    if (-not $script:SolutionFile -or -not (Test-Path $script:SolutionFile)) {
        Write-Host "  ERROR: Solution file not found" -ForegroundColor Red
        return $false
    }

    Write-Host "  Solution: $($script:SolutionFile)" -ForegroundColor Gray

    # Run dotnet build
    $buildProcess = Start-Process -FilePath "dotnet" `
        -ArgumentList "build", $script:SolutionFile, "--configuration", "Debug" `
        -WorkingDirectory $BackendDir `
        -PassThru `
        -NoNewWindow `
        -Wait

    if ($buildProcess.ExitCode -ne 0) {
        Write-Host "  ERROR: Build failed with exit code $($buildProcess.ExitCode)" -ForegroundColor Red
        return $false
    }

    Write-Host "  Build completed successfully" -ForegroundColor Green
    return $true
}

function Start-BackendServer {
    Write-Host "  Starting backend server..." -ForegroundColor Yellow

    if (-not $script:WebHostProject -or -not (Test-Path $script:WebHostProject)) {
        Write-Host "  ERROR: Web.Host project not found" -ForegroundColor Red
        return $null
    }

    Write-Host "  Project: $($script:WebHostProject)" -ForegroundColor Gray

    # Start server in background with --launch-profile Project and visible output
    # Using -NoNewWindow keeps stdout/stderr in the current console for diagnosing
    # startup errors, migration failures, binding issues, etc.
    $process = Start-Process -FilePath "dotnet" `
        -ArgumentList "run", "--project", $script:WebHostProject, "--no-build", "--launch-profile", "Project" `
        -WorkingDirectory $BackendDir `
        -PassThru `
        -NoNewWindow

    Write-Host "  Server process started (PID: $($process.Id))" -ForegroundColor Gray
    return $process
}

function Stop-BackendServer {
    param($Process)
    if ($Process -and -not $Process.HasExited) {
        Write-Host "  Stopping server (PID: $($Process.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  Server stopped" -ForegroundColor Green
    }
}

function Find-DomainEntities {
    Write-Host "  Scanning domain folder for entities..." -ForegroundColor Yellow

    $entities = @()

    $pathsToScan = if ($script:DomainPaths.Count -gt 0) { $script:DomainPaths } elseif ($script:DomainPath) { @($script:DomainPath) } else { @() }

    if ($pathsToScan.Count -eq 0) {
        Write-Host "  WARNING: Domain path not found" -ForegroundColor Yellow
        return $entities
    }

    foreach ($domainPath in $pathsToScan) {
        Write-Host "  Domain path: $domainPath" -ForegroundColor Gray
    }

    # Find all .cs files across all Domain folders
    $csFiles = @()
    foreach ($domainPath in $pathsToScan) {
        if (Test-Path $domainPath) {
            $csFiles += Get-ChildItem -Path $domainPath -Filter "*.cs" -Recurse
        }
    }

    foreach ($file in $csFiles) {
        $content = Get-Content $file.FullName -Raw

        # Skip pure enum/reference list definition files (not entity files that use reference lists)
        if ($content -match 'public enum ') {
            continue
        }

        # Look for classes with [Entity] attribute
        if ($content -match '\[Entity\(') {
            # Extract namespace
            if ($content -match 'namespace\s+([\w\.]+)') {
                $namespace = $Matches[1]
            }
            else {
                continue
            }

            # Extract class name - look for public class that extends something
            if ($content -match 'public\s+class\s+(\w+)\s*:\s*\w+') {
                $className = $Matches[1]
                $fullType = "$namespace.$className"

                # Create short display name
                $displayName = $className
                if ($displayName.Length -gt 20) {
                    $displayName = $className.Substring(0, 17) + "..."
                }

                $entities += [PSCustomObject]@{
                    FullType = $fullType
                    ClassName = $className
                    DisplayName = $displayName
                    FilePath = $file.FullName
                }
            }
        }
    }

    Write-Host "  Found $($entities.Count) entities with [Entity] attribute" -ForegroundColor Green
    return $entities
}

function Update-TestScript {
    param($Entities)

    $testScriptPath = Join-Path $ScriptDir "Test-Endpoints.ps1"

    if (-not (Test-Path $testScriptPath)) {
        Write-Host "  ERROR: Test script not found: $testScriptPath" -ForegroundColor Red
        return $false
    }

    # Generate the new entities array
    $entityLines = @()
    foreach ($entity in $Entities | Sort-Object ClassName) {
        $displayName = $entity.ClassName
        if ($displayName.Length -gt 20) {
            $displayName = $displayName.Substring(0, 20)
        }
        $entityLines += "    @{ Type = `"$($entity.FullType)`"; Name = `"$displayName`" }"
    }

    $entitiesBlock = $entityLines -join "`n"

    # Read the current script
    $scriptContent = Get-Content $testScriptPath -Raw

    # Find and replace the $Entities array
    $pattern = '(?s)\$Entities = @\(\s*(@\{[^)]+\}\s*)+\)'
    $replacement = "`$Entities = @(`n$entitiesBlock`n)"

    if ($scriptContent -match $pattern) {
        $newContent = $scriptContent -replace $pattern, $replacement
        Set-Content -Path $testScriptPath -Value $newContent -NoNewline
        Write-Host "  Updated Test-Endpoints.ps1 with $($Entities.Count) entities" -ForegroundColor Green
        return $true
    }
    else {
        Write-Host "  WARNING: Could not find entities array in test script" -ForegroundColor Yellow
        return $false
    }
}

# ============================================================================
# Main Execution
# ============================================================================

Clear-Host
Write-Header "Shesha Project - Endpoint Test Runner"

# Verify backend directory exists
if (-not (Test-Path $BackendDir)) {
    Write-Host "  ERROR: Backend directory not found at $BackendDir" -ForegroundColor Red
    Write-Host "  Please run this script from within the repository or specify -RepoRoot" -ForegroundColor Yellow
    exit 1
}

# Auto-detect project files
Write-Host "  Detecting project structure..." -ForegroundColor Yellow
if (-not (Find-ProjectFiles)) {
    Write-Host "  ERROR: Failed to detect project structure" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Configuration:" -ForegroundColor Gray
Write-Host "    Project:         $($script:ProjectName)"
Write-Host "    Server URL:      $BaseUrl"
Write-Host "    Username:        $Username"
Write-Host "    Repo Root:       $RepoRoot"
Write-Host "    Backend Dir:     $BackendDir"
Write-Host "    Solution:        $($script:SolutionFile)"
Write-Host "    Web.Host:        $($script:WebHostProject)"
Write-Host "    Domain Path:     $($script:DomainPath)"
Write-Host "    Update Entities: $UpdateEntities"
Write-Host "    Full Errors:     $FullErrors"
Write-Host ""

# Step 0: Update entities if requested
if ($UpdateEntities) {
    Write-Header "Scanning for Domain Entities"

    $foundEntities = Find-DomainEntities

    if ($foundEntities.Count -gt 0) {
        Write-Host ""
        Write-Host "  Entities found:" -ForegroundColor Gray
        foreach ($entity in $foundEntities | Sort-Object ClassName) {
            Write-Host "    - $($entity.ClassName)" -ForegroundColor White
        }
        Write-Host ""

        if (Update-TestScript -Entities $foundEntities) {
            Write-Host "  Entity list updated successfully" -ForegroundColor Green
        }
    }
    else {
        Write-Host "  No entities found to update" -ForegroundColor Yellow
    }
}

# Step 1: Check if server is running and handle startup
Write-Host "  Checking server status..." -ForegroundColor Yellow
$serverWasRunning = Test-ServerRunning

if ($StartServer) {
    # -StartServer always rebuilds and starts a fresh server
    if ($serverWasRunning) {
        Write-Status "Server status:" "RUNNING (stale - will restart with new code)" "Yellow"
        Write-Host "  Stopping existing server to rebuild with latest changes..." -ForegroundColor Yellow
        # Find and kill the existing dotnet Web.Host process
        $existingProcesses = Get-Process -Name "dotnet" -ErrorAction SilentlyContinue |
            Where-Object { $_.MainModule.FileName -match "dotnet" }
        foreach ($proc in $existingProcesses) {
            try {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                Write-Host "  Stopped existing dotnet process (PID: $($proc.Id))" -ForegroundColor Yellow
            } catch { }
        }
        Start-Sleep -Seconds 2
    }
    else {
        Write-Status "Server status:" "NOT RUNNING" "Red"
    }

    Write-Host ""

    # Build the solution first
    if (-not (Build-Backend)) {
        Write-Host "  ERROR: Build failed, cannot start server" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    $ServerProcess = Start-BackendServer

    if ($ServerProcess) {
        if (-not (Wait-ForServer -TimeoutSeconds $StartupTimeoutSeconds)) {
            Write-Host ""
            Write-Host "  ERROR: Server failed to start within timeout period" -ForegroundColor Red
            Stop-BackendServer -Process $ServerProcess
            exit 1
        }
    }
    else {
        Write-Host "  ERROR: Failed to start server process" -ForegroundColor Red
        exit 1
    }
}
elseif ($serverWasRunning) {
    Write-Status "Server status:" "RUNNING" "Green"
}
else {
    Write-Status "Server status:" "NOT RUNNING" "Red"
    Write-Host ""
    Write-Host "  The backend server is not running." -ForegroundColor Yellow
    Write-Host "  Options:" -ForegroundColor Yellow
    Write-Host "    1. Start the server manually: dotnet run --project $($script:WebHostProject)" -ForegroundColor Gray
    Write-Host "    2. Run this script with -StartServer flag to auto-start" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Example: .\Run-EndpointTests.ps1 -StartServer" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# Step 2: Run the endpoint tests
Write-Header "Running Endpoint Tests"

$testScript = Join-Path $ScriptDir "Test-Endpoints.ps1"

if (-not (Test-Path $testScript)) {
    Write-Host "  ERROR: Test script not found at $testScript" -ForegroundColor Red
    if ($ServerProcess) { Stop-BackendServer -Process $ServerProcess }
    exit 1
}

$testExitCode = 0
try {
    $testParams = @{
        BaseUrl = $BaseUrl
        Username = $Username
        Password = $Password
    }
    if ($FullErrors) {
        $testParams.FullErrors = $true
    }
    & $testScript @testParams
    $testExitCode = $LASTEXITCODE
}
catch {
    Write-Host "  ERROR: Test execution failed - $_" -ForegroundColor Red
    $testExitCode = 1
}
finally {
    # Always clean up the server we started, even on crash/abort
    if ($ServerProcess) {
        Write-Host ""
        Write-Header "Cleanup"
        Stop-BackendServer -Process $ServerProcess
    }
}

# Step 3: Final summary
Write-Host ""
if ($testExitCode -eq 0) {
    Write-Host "  All tests passed!" -ForegroundColor Green
}
else {
    Write-Host "  $testExitCode endpoint(s) failed. See details above." -ForegroundColor Yellow
}
Write-Host ""

exit $testExitCode

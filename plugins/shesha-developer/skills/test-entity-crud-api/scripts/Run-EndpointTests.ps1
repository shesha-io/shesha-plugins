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
    [string]$RepoRoot = "",
    # Comma-separated list of module names to test (substring match against the owning
    # *.Domain project name / namespace, case-insensitive). Empty = all modules.
    [string]$Modules = "",
    # Comma-separated list of entity class names to test (exact match, case-insensitive).
    # Empty = all entities. Combined with -Modules as an intersection.
    [string]$Entities = ""
)

# Parse the comma-separated filter lists into trimmed, non-empty token arrays.
$ModuleFilter = @($Modules -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$EntityFilter = @($Entities -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })

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
        # Look for "Project" profile first, then fall back to first profile
        $projectProfile = $null
        if ($json.profiles.PSObject.Properties["Project"]) {
            $projectProfile = $json.profiles.Project
        } else {
            $profiles = $json.profiles.PSObject.Properties | Select-Object -First 1
            if ($profiles) { $projectProfile = $profiles.Value }
        }
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
$script:DomainPath = $null          # first domain folder found (kept for display/back-compat)
$script:DomainProjects = @()        # all domain folders: @{ Module = "<name>"; Path = "<Domain folder>" }
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

    # Find ALL Domain folders - every *.Domain project that has a Domain subfolder.
    # (Previously only the first match was kept, so multi-module repos were under-scanned.)
    $domainProjects = Get-ChildItem -Path $BackendDir -Filter "*.Domain.csproj" -Recurse -ErrorAction SilentlyContinue
    $collected = @()
    foreach ($proj in $domainProjects) {
        $domainFolder = Join-Path $proj.DirectoryName "Domain"
        if (Test-Path $domainFolder) {
            # Module name = project file name without the trailing ".Domain" (e.g. Shesha.ProjectOps.Domain -> Shesha.ProjectOps)
            $moduleName = [System.IO.Path]::GetFileNameWithoutExtension($proj.Name) -replace '\.Domain$', ''
            $collected += [PSCustomObject]@{ Module = $moduleName; Path = $domainFolder }
        }
    }

    if ($collected.Count -eq 0) {
        # Fallback: look for any folder named "Domain" under src whose parent project ends in .Domain
        $srcPath = Join-Path $BackendDir "src"
        if (Test-Path $srcPath) {
            $domainFolders = Get-ChildItem -Path $srcPath -Directory -Recurse -Filter "Domain" -ErrorAction SilentlyContinue |
                Where-Object { $_.Parent.Name -match '\.Domain$' }
            foreach ($df in $domainFolders) {
                $moduleName = $df.Parent.Name -replace '\.Domain$', ''
                $collected += [PSCustomObject]@{ Module = $moduleName; Path = $df.FullName }
            }
        }
    }

    $script:DomainProjects = $collected
    if ($collected.Count -gt 0) {
        $script:DomainPath = $collected[0].Path
    }

    if (-not $script:DomainProjects -or $script:DomainProjects.Count -eq 0) {
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
    Write-Host "  Scanning domain folders for entities..." -ForegroundColor Yellow

    $entities = @()

    if (-not $script:DomainProjects -or $script:DomainProjects.Count -eq 0) {
        Write-Host "  WARNING: No domain paths found" -ForegroundColor Yellow
        return ,$entities
    }

    foreach ($dp in $script:DomainProjects) {
        Write-Host "  Module '$($dp.Module)' -> $($dp.Path)" -ForegroundColor Gray
    }

    # Known Shesha / ABP entity base patterns. Matched against the *first* base type
    # in a class declaration (after `:`). Generic args are stripped before matching.
    $entityBasePatterns = @(
        '^FullAuditedEntity$',
        '^Entity$',
        '^AuditedEntity$',
        '^CreationAuditedEntity$',
        '^ConfigurationItemBase$',
        '^WorkflowDefinition$',
        '^WorkflowInstance$',
        '^WorkflowInstanceWithTypedDefinition$'
    )

    $classMap = @{}

    # First pass: index every class declaration across ALL module domain folders, with
    # its first base type and owning module. Building the map across modules lets derived
    # chains that cross module boundaries (e.g. ProjOpsTimesheetLine : TimesheetLine) resolve.
    foreach ($dp in $script:DomainProjects) {
        if (-not (Test-Path $dp.Path)) { continue }
        $csFiles = Get-ChildItem -Path $dp.Path -Filter "*.cs" -Recurse

        foreach ($file in $csFiles) {
            $content = Get-Content $file.FullName -Raw

            # Skip enum-only files. Do NOT key off [ReferenceList(...)] — it's
            # commonly used as a *property* attribute on entity classes.
            if ($content -match 'public\s+enum\s+' -and $content -notmatch 'public\s+(abstract\s+|sealed\s+|partial\s+)*class\s+') { continue }

            $nsMatch = [regex]::Match($content, 'namespace\s+([\w\.]+)')
            if (-not $nsMatch.Success) { continue }
            $namespace = $nsMatch.Groups[1].Value

            # Match class declarations; capture abstract modifier, class name, base list
            $classRe = '(?m)public\s+(abstract\s+)?(sealed\s+)?(partial\s+)?class\s+(\w+)\s*(?:<[^>]+>)?\s*(?::\s*([^\r\n{]+))?'
            $classMatches = [regex]::Matches($content, $classRe)

            foreach ($m in $classMatches) {
                $isAbstract = $m.Groups[1].Success
                $className  = $m.Groups[4].Value
                $baseList   = if ($m.Groups[5].Success) { $m.Groups[5].Value.Trim() } else { '' }

                # First entry in base list (skip generic args, trim whitespace)
                $firstBase = ''
                if ($baseList) {
                    $firstBase = ($baseList -split ',')[0].Trim()
                    $firstBase = ($firstBase -split '<')[0].Trim()
                }

                $hasEntityAttr = ($content -match "\[Entity\([^)]*\)\]\s*public\s+(abstract\s+|sealed\s+|partial\s+)*class\s+$className\b")

                $classMap[$className] = @{
                    Namespace     = $namespace
                    BaseClass     = $firstBase
                    IsAbstract    = $isAbstract
                    HasEntityAttr = $hasEntityAttr
                    File          = $file.FullName
                    Module        = $dp.Module
                }
            }
        }
    }

    # Resolve whether a base-class chain ends in a Shesha/ABP entity base.
    # Walks the local class map so derived chains like Foo : Bar : FullAuditedEntity resolve correctly.
    function script:Resolve-IsEntityBase {
        param([string]$BaseName, [hashtable]$Map, [string[]]$Patterns, [System.Collections.Generic.HashSet[string]]$Seen)
        if (-not $BaseName) { return $false }
        if ($Seen.Contains($BaseName)) { return $false }
        [void]$Seen.Add($BaseName)
        foreach ($p in $Patterns) {
            if ($BaseName -match $p) { return $true }
        }
        if ($Map.ContainsKey($BaseName)) {
            return script:Resolve-IsEntityBase -BaseName $Map[$BaseName].BaseClass -Map $Map -Patterns $Patterns -Seen $Seen
        }
        return $false
    }

    # Second pass: pick concrete entities (skip abstract; require entity base chain OR explicit [Entity] attribute)
    foreach ($entry in $classMap.GetEnumerator()) {
        $className = $entry.Key
        $info      = $entry.Value

        if ($info.IsAbstract) { continue }

        $seen = New-Object 'System.Collections.Generic.HashSet[string]'
        $isEntity = $info.HasEntityAttr -or (script:Resolve-IsEntityBase -BaseName $info.BaseClass -Map $classMap -Patterns $entityBasePatterns -Seen $seen)
        if (-not $isEntity) { continue }

        $displayName = if ($className.Length -gt 40) { $className.Substring(0, 37) + '...' } else { $className }

        $entities += [PSCustomObject]@{
            FullType    = "$($info.Namespace).$className"
            ClassName   = $className
            DisplayName = $displayName
            FilePath    = $info.File
            Module      = $info.Module
        }
    }

    Write-Host "  Found $($entities.Count) entities across $($script:DomainProjects.Count) module(s)" -ForegroundColor Green
    # Comma prefix prevents PowerShell from unwrapping a single-element array on return
    return ,$entities
}

function Select-FilteredEntities {
    <#
    .SYNOPSIS
    Apply the -Modules / -Entities filters to a scanned entity list.
    Module tokens are matched as case-insensitive substrings against the owning module
    name OR the entity namespace. Entity tokens are matched case-insensitively against
    the class name (exact). Both filters combine as an intersection. Empty filter = no
    restriction on that axis.
    #>
    param($AllEntities, [string[]]$ModuleTokens, [string[]]$EntityTokens)

    $selected = $AllEntities

    if ($ModuleTokens.Count -gt 0) {
        $selected = $selected | Where-Object {
            $ent = $_
            ($ModuleTokens | Where-Object {
                $ent.Module -and ($ent.Module -ilike "*$_*" -or $ent.FullType -ilike "*$_*")
            }).Count -gt 0
        }
    }

    if ($EntityTokens.Count -gt 0) {
        $selected = $selected | Where-Object {
            $ent = $_
            ($EntityTokens | Where-Object { $ent.ClassName -ieq $_ }).Count -gt 0
        }
    }

    return ,@($selected)
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
        if ($displayName.Length -gt 40) {
            $displayName = $displayName.Substring(0, 40)
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
Write-Host "    Domain Modules:  $($script:DomainProjects.Count) found"
Write-Host "    Update Entities: $UpdateEntities"
Write-Host "    Full Errors:     $FullErrors"
Write-Host "    Module Filter:   $(if ($ModuleFilter.Count) { $ModuleFilter -join ', ' } else { '(all)' })"
Write-Host "    Entity Filter:   $(if ($EntityFilter.Count) { $EntityFilter -join ', ' } else { '(all)' })"
Write-Host ""

# Step 0: Update entities if requested. Filters imply a scan even without -UpdateEntities,
# since the testable list is regenerated from the (filtered) scan results.
if ($UpdateEntities -or $ModuleFilter.Count -gt 0 -or $EntityFilter.Count -gt 0) {
    Write-Header "Scanning for Domain Entities"

    $foundEntities = Find-DomainEntities

    # Apply module / entity filters to the scanned list.
    $filteredEntities = Select-FilteredEntities -AllEntities $foundEntities -ModuleTokens $ModuleFilter -EntityTokens $EntityFilter

    if (($ModuleFilter.Count -gt 0 -or $EntityFilter.Count -gt 0)) {
        Write-Host ""
        Write-Host "  Filter selected $($filteredEntities.Count) of $($foundEntities.Count) scanned entities." -ForegroundColor Cyan

        # Warn about filter tokens that matched nothing - silent under-testing is a trap.
        foreach ($tok in $EntityFilter) {
            if (($foundEntities | Where-Object { $_.ClassName -ieq $tok }).Count -eq 0) {
                Write-Host "  WARNING: entity filter '$tok' matched no scanned entity." -ForegroundColor Yellow
            }
        }
        foreach ($tok in $ModuleFilter) {
            if (($foundEntities | Where-Object { $_.Module -ilike "*$tok*" -or $_.FullType -ilike "*$tok*" }).Count -eq 0) {
                Write-Host "  WARNING: module filter '$tok' matched no scanned module/entity." -ForegroundColor Yellow
            }
        }
    }

    if ($filteredEntities.Count -gt 0) {
        Write-Host ""
        Write-Host "  Entities to test:" -ForegroundColor Gray
        foreach ($entity in $filteredEntities | Sort-Object Module, ClassName) {
            Write-Host "    - [$($entity.Module)] $($entity.ClassName)" -ForegroundColor White
        }
        Write-Host ""

        if (Update-TestScript -Entities $filteredEntities) {
            Write-Host "  Entity list updated successfully" -ForegroundColor Green
        }
    }
    else {
        Write-Host "  No entities selected to test (check your --modules / --entities filters)." -ForegroundColor Yellow
    }
}

# Step 1: Check if server is running
Write-Host "  Checking server status..." -ForegroundColor Yellow
$serverWasRunning = Test-ServerRunning

if ($serverWasRunning) {
    Write-Status "Server status:" "RUNNING" "Green"
}
else {
    Write-Status "Server status:" "NOT RUNNING" "Red"

    if ($StartServer) {
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
    else {
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
}

# Step 2: Run the endpoint tests
Write-Header "Running Endpoint Tests"

$testScript = Join-Path $ScriptDir "Test-Endpoints.ps1"

if (-not (Test-Path $testScript)) {
    Write-Host "  ERROR: Test script not found at $testScript" -ForegroundColor Red
    if ($ServerProcess) { Stop-BackendServer -Process $ServerProcess }
    exit 1
}

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

# Step 3: Cleanup if we started the server
if ($ServerProcess) {
    Write-Host ""
    Write-Header "Cleanup"
    Stop-BackendServer -Process $ServerProcess
}

# Step 4: Final summary
Write-Host ""
if ($testExitCode -eq 0) {
    Write-Host "  All tests passed!" -ForegroundColor Green
}
else {
    Write-Host "  $testExitCode endpoint(s) failed. See details above." -ForegroundColor Yellow
}
Write-Host ""

exit $testExitCode

<#
.SYNOPSIS
    Builds, starts, and tests the Shesha backend server.
.DESCRIPTION
    Builds the solution, starts the server with --urls flag, uses TCP port polling
    instead of blind sleeps, checks for DB errors and auto-restores if needed,
    tests authentication with credential cascade, then cleans up.
    Outputs structured JSON for Claude to parse.
.PARAMETER SlnPath
    Full path to the .sln file.
.PARAMETER WebHostProject
    Full path to the Web.Host project directory.
.PARAMETER BackendPort
    Port the backend listens on. Defaults to 21021.
.PARAMETER Username
    Login username. Defaults to 'admin'.
.PARAMETER Password
    Login password. Defaults to '123qwe'.
.PARAMETER BacpacPath
    Optional path to .bacpac file for database restore.
.PARAMETER DatabaseName
    Database name for restore operations.
.PARAMETER ScriptsDir
    Path to the scripts directory (for calling Restore-Database.ps1).
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$SlnPath,

    [Parameter(Mandatory = $true)]
    [string]$WebHostProject,

    [int]$BackendPort = 21021,

    [string]$Username = 'admin',

    [string]$Password = '123qwe',

    [string]$BacpacPath = '',

    [string]$DatabaseName = '',

    [string]$ScriptsDir = ''
)

$ErrorActionPreference = 'Stop'

# --- Helper: Wait-ForPort ---
function Wait-ForPort {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 120,
        [int]$IntervalSeconds = 2
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect('127.0.0.1', $Port)
            $tcp.Close()
            return $true
        }
        catch {
            Start-Sleep -Seconds $IntervalSeconds
        }
    }
    return $false
}

# --- Helper: Stop-ServerJob ---
function Stop-ServerJob {
    param($Job)
    if ($Job -and $Job.State -eq 'Running') {
        Stop-Job $Job -ErrorAction SilentlyContinue
    }
    if ($Job) {
        Remove-Job $Job -Force -ErrorAction SilentlyContinue
    }
    # Kill any orphan dotnet processes on our port
    $portListeners = netstat -ano 2>$null | Select-String ":$BackendPort\s" |
        ForEach-Object {
            if ($_ -match '\s(\d+)$') { [int]$Matches[1] }
        } | Sort-Object -Unique
    foreach ($procId in $portListeners) {
        if ($procId -gt 0) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

# --- Helper: Get-JobOutput ---
function Get-JobOutput {
    param($Job, [int]$TailLines = 30)
    $output = @()
    if ($Job) {
        try { $output += Receive-Job $Job -ErrorAction SilentlyContinue 2>&1 | ForEach-Object { $_.ToString() } } catch {}
    }
    if ($output.Count -gt $TailLines) {
        $output = $output[($output.Count - $TailLines)..($output.Count - 1)]
    }
    return ($output -join "`n")
}

# --- Helper: Test-Authentication ---
function Test-Authentication {
    param(
        [string]$Url,
        [string]$User,
        [string]$Pass
    )
    try {
        $body = @{
            userNameOrEmailAddress = $User
            password               = $Pass
        } | ConvertTo-Json

        $response = Invoke-WebRequest -Uri "$Url/api/TokenAuth/Authenticate" `
            -Method POST `
            -ContentType 'application/json' `
            -Body $body `
            -UseBasicParsing `
            -TimeoutSec 15 `
            -ErrorAction Stop

        $data = $response.Content | ConvertFrom-Json
        if ($data.success -or $data.result) {
            return @{ success = $true; message = 'Authentication successful' }
        }
        return @{ success = $false; message = "Unexpected response: $($response.StatusCode)" }
    }
    catch {
        $statusCode = 0
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        return @{
            success = $false
            message = "Auth failed (HTTP $statusCode): $($_.Exception.Message)"
        }
    }
}

# --- Main ---
$result = @{
    build             = 'SKIP'
    server            = 'SKIP'
    auth              = 'SKIP'
    credentials       = @{
        username = $Username
        password = $Password
        source   = 'provided'
    }
    databaseRestored  = $false
    serverOutput      = ''
    errors            = @()
}

$serverJob = $null
$backendUrl = "http://localhost:$BackendPort"

try {
    # --- Step 1: Build ---
    Write-Host "Building solution: $SlnPath"
    $buildOutput = & dotnet build $SlnPath 2>&1
    $buildExitCode = $LASTEXITCODE
    $buildLines = ($buildOutput | ForEach-Object { $_.ToString() })

    if ($buildExitCode -ne 0) {
        $result.build = 'FAIL'
        # Capture last 30 lines
        if ($buildLines.Count -gt 30) {
            $buildLines = $buildLines[($buildLines.Count - 30)..($buildLines.Count - 1)]
        }
        $result.errors += "Build failed (exit code $buildExitCode)"
        $result.serverOutput = ($buildLines -join "`n")
        $result | ConvertTo-Json -Depth 5
        exit 0
    }
    $result.build = 'PASS'
    Write-Host 'Build succeeded.'

    # --- Step 2: Start server ---
    Write-Host "Starting backend server on port $BackendPort..."
    $webHostCsproj = Get-ChildItem -Path $WebHostProject -Filter '*.csproj' | Select-Object -First 1
    $projectArg = if ($webHostCsproj) { $webHostCsproj.FullName } else { $WebHostProject }

    $serverJob = Start-Job -ScriptBlock {
        param($proj, $port)
        Set-Location (Split-Path $proj -Parent)
        & dotnet run --project $proj --urls "http://localhost:$port" --no-build 2>&1
    } -ArgumentList $projectArg, $BackendPort

    Write-Host 'Waiting for server to start (polling port)...'
    $portReady = Wait-ForPort -Port $BackendPort -TimeoutSeconds 600

    if (-not $portReady) {
        $result.server = 'FAIL'
        $result.serverOutput = Get-JobOutput -Job $serverJob -TailLines 30
        $result.errors += 'Server did not start within 600 seconds'

        # Check for database errors
        $jobOutput = $result.serverOutput
        $isDbError = $jobOutput -match '(?i)(cannot open database|login failed|connection.*refused|Initial Catalog|network-related)'

        if ($isDbError -and $BacpacPath -and $DatabaseName) {
            Write-Host 'Detected database error, attempting restore...'
            Stop-ServerJob -Job $serverJob
            $serverJob = $null

            # Call Restore-Database.ps1
            $restoreScript = Join-Path $ScriptsDir 'Restore-Database.ps1'
            if (Test-Path $restoreScript) {
                $restoreOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $restoreScript `
                    -BacpacPath $BacpacPath `
                    -TargetDatabase $DatabaseName 2>&1
                $restoreResult = ($restoreOutput | ForEach-Object { $_.ToString() }) -join '' | ConvertFrom-Json

                if ($restoreResult.success) {
                    $result.databaseRestored = $true
                    Write-Host 'Database restored, restarting server...'

                    # Restart server
                    $serverJob = Start-Job -ScriptBlock {
                        param($proj, $port)
                        Set-Location (Split-Path $proj -Parent)
                        & dotnet run --project $proj --urls "http://localhost:$port" --no-build 2>&1
                    } -ArgumentList $projectArg, $BackendPort

                    $portReady = Wait-ForPort -Port $BackendPort -TimeoutSeconds 600
                    if ($portReady) {
                        $result.server = 'PASS'
                        $result.errors = @($result.errors | Where-Object { $_ -notmatch 'did not start' })
                    }
                    else {
                        $result.serverOutput = Get-JobOutput -Job $serverJob -TailLines 30
                        $result.errors += 'Server failed to start after database restore (timeout)'
                    }
                }
                else {
                    $result.errors += "Database restore failed: $($restoreResult.message)"
                }
            }
            else {
                $result.errors += 'Restore-Database.ps1 not found, cannot auto-restore'
            }
        }

        if ($result.server -ne 'PASS') {
            $result | ConvertTo-Json -Depth 5
            Stop-ServerJob -Job $serverJob
            exit 0
        }
    }
    else {
        $result.server = 'PASS'
        Write-Host 'Server is listening.'
    }

    # --- Step 3: Authentication ---
    Write-Host "Testing authentication as '$Username'..."
    $authResult = Test-Authentication -Url $backendUrl -User $Username -Pass $Password

    if (-not $authResult.success) {
        # Try default credentials if different from provided
        if ($Username -ne 'admin' -or $Password -ne '123qwe') {
            Write-Host 'Provided credentials failed, trying default admin/123qwe...'
            $defaultAuth = Test-Authentication -Url $backendUrl -User 'admin' -Pass '123qwe'
            if ($defaultAuth.success) {
                $authResult = $defaultAuth
                $result.credentials = @{
                    username = 'admin'
                    password = '123qwe'
                    source   = 'default'
                }
            }
        }
    }

    if ($authResult.success) {
        $result.auth = 'PASS'
        Write-Host 'Authentication successful.'
    }
    else {
        $result.auth = 'FAIL'
        $result.errors += $authResult.message
    }

    $result.serverOutput = Get-JobOutput -Job $serverJob -TailLines 15

} catch {
    $result.errors += "Unexpected error: $($_.Exception.Message)"
} finally {
    # --- Cleanup ---
    Write-Host 'Stopping server...'
    Stop-ServerJob -Job $serverJob
}

$result | ConvertTo-Json -Depth 5

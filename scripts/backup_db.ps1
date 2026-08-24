[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-Sha256Hex {
    param([Parameter(Mandatory)][string]$Path)
    $stream = $null
    $algorithm = $null
    try {
        $stream = [IO.File]::Open(
            $Path,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::Read
        )
        $algorithm = [Security.Cryptography.SHA256]::Create()
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace("-", "").ToLowerInvariant()
    } finally {
        if ($null -ne $algorithm) { $algorithm.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Invoke-DockerCommand {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker_command_failed"
    }
}

function Invoke-DockerCapture {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $output = @(& docker @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "docker_command_failed"
    }
    return ($output -join "`n").Trim()
}

function Get-ContainerIdentifier {
    param(
        [Parameter(Mandatory)][string]$VariableName,
        [Parameter(Mandatory)][string]$ErrorCode
    )
    $value = Invoke-DockerCapture -Arguments ($composePrefix + @(
        "exec", "-T", "db", "printenv", $VariableName
    ))
    if ([string]::IsNullOrWhiteSpace($value) -or $value.Length -gt 63 -or $value -notmatch '^[A-Za-z_][A-Za-z0-9_]{0,62}$') {
        throw $ErrorCode
    }
    return $value
}

function Get-InstallationIdentifier {
    $value = Invoke-DockerCapture -Arguments ($composePrefix + @(
        "exec", "-T", "db", "printenv", "INSTALLATION_ID"
    ))
    if (
        $value -eq '00000000-0000-4000-8000-000000000000' -or
        $value -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    ) {
        throw "invalid_INSTALLATION_ID"
    }
    return $value
}

function Set-PrivatePermissions {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][bool]$Directory
    )
    $isWindows = $env:OS -eq "Windows_NT" -or [IO.Path]::DirectorySeparatorChar -eq '\'
    if ($isWindows) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $grant = if ($Directory) { "${identity}:(OI)(CI)F" } else { "${identity}:F" }
        & icacls.exe $Path /inheritance:r /grant:r $grant | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "backup_permissions_failed" }
    } else {
        $mode = if ($Directory) { "700" } else { "600" }
        & chmod $mode -- $Path
        if ($LASTEXITCODE -ne 0) { throw "backup_permissions_failed" }
    }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$composePrefix = @("compose", "--project-directory", $repoRoot)
$databaseName = Get-ContainerIdentifier -VariableName "POSTGRES_DB" -ErrorCode "invalid_POSTGRES_DB"
$databaseUser = Get-ContainerIdentifier -VariableName "POSTGRES_USER" -ErrorCode "invalid_POSTGRES_USER"
$installationId = Get-InstallationIdentifier
$backupsPath = Join-Path $repoRoot "backups"
if (Test-Path -LiteralPath $backupsPath) {
    $backupsItem = Get-Item -LiteralPath $backupsPath -Force
    if (($backupsItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "backups_path_symlink_not_allowed"
    }
} else {
    $null = New-Item -ItemType Directory -Path $backupsPath
}
Set-PrivatePermissions -Path $backupsPath -Directory $true
$backupsRoot = (Resolve-Path -LiteralPath $backupsPath).Path
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss-fff")
$nonce = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$backupPath = Join-Path $backupsRoot "diagnostic-$timestamp-$nonce.dump"
$hostTemp = Join-Path $backupsRoot ".$([IO.Path]::GetFileName($backupPath)).$([Guid]::NewGuid().ToString('N')).tmp"
$checksumPath = "$backupPath.sha256"
$manifestPath = "$backupPath.manifest.json"
$checksumTemp = "$hostTemp.sha256"
$manifestTemp = "$hostTemp.manifest.json"
$published = $false
$createdFinals = [Collections.Generic.List[string]]::new()
if (Test-Path -LiteralPath $backupPath) {
    throw "backup_already_exists"
}

$containerTemp = "/tmp/diagnostic-backup-$([Guid]::NewGuid().ToString('N')).dump"
try {
    Invoke-DockerCommand -Arguments ($composePrefix + @(
        "exec", "-T", "db", "sh", "-ceu",
        'pg_dump --format=custom --no-owner --no-privileges --username="$1" --dbname="$2" --file="$3"',
        "sh", $databaseUser, $databaseName, $containerTemp
    ))
    Invoke-DockerCommand -Arguments ($composePrefix + @(
        "exec", "-T", "db", "pg_restore", "--list", $containerTemp
    ))
    # docker compose cp keeps the custom-format archive binary-safe.
    Invoke-DockerCommand -Arguments ($composePrefix + @("cp", "db:$containerTemp", $hostTemp))
    $backupItem = Get-Item -LiteralPath $hostTemp
    if ($backupItem.PSIsContainer -or $backupItem.Length -le 0) {
        throw "backup_validation_failed"
    }
    $checksum = Get-Sha256Hex -Path $hostTemp
    [IO.File]::WriteAllText(
        $checksumTemp,
        "$checksum  $([IO.Path]::GetFileName($backupPath))`n",
        [Text.UTF8Encoding]::new($false)
    )
    $manifest = [ordered]@{
        format = 2
        archive = [IO.Path]::GetFileName($backupPath)
        database = $databaseName
        installation_id = $installationId
        sha256 = $checksum
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($manifestTemp, "$manifest`n", [Text.UTF8Encoding]::new($false))
    foreach ($privateFile in @($hostTemp, $checksumTemp, $manifestTemp)) {
        Set-PrivatePermissions -Path $privateFile -Directory $false
    }
    Move-Item -LiteralPath $checksumTemp -Destination $checksumPath
    $createdFinals.Add($checksumPath)
    Move-Item -LiteralPath $manifestTemp -Destination $manifestPath
    $createdFinals.Add($manifestPath)
    Move-Item -LiteralPath $hostTemp -Destination $backupPath
    $createdFinals.Add($backupPath)
    $published = $true
    Write-Output "Backup created: $backupPath"
} finally {
    foreach ($temporary in @($hostTemp, $checksumTemp, $manifestTemp)) {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
    if (-not $published) {
        foreach ($partial in $createdFinals) {
            if (Test-Path -LiteralPath $partial) {
                Remove-Item -LiteralPath $partial -Force
            }
        }
    }
    & docker @composePrefix exec -T db rm -f -- $containerTemp | Out-Null
}

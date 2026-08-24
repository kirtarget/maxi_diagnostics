[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$BackupPath,
    [switch]$ConfirmRestore
)

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

if (-not $ConfirmRestore) {
    throw "restore_requires_ConfirmRestore"
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$composeFiles = [Collections.Generic.List[string]]::new()
$composeFiles.Add((Join-Path $repoRoot "docker-compose.yml"))
$productionComposePath = Join-Path $repoRoot "deploy/docker-compose.production.yml"
if (Test-Path -LiteralPath $productionComposePath -PathType Leaf) {
    $composeFiles.Add($productionComposePath)
}
$composePrefix = @("compose", "--project-directory", $repoRoot)
foreach ($composeFile in $composeFiles) {
    $composePrefix += @("-f", $composeFile)
}
$backupsPath = Join-Path $repoRoot "backups"
if (-not (Test-Path -LiteralPath $backupsPath -PathType Container)) {
    throw "backups_path_not_found"
}
$backupsItem = Get-Item -LiteralPath $backupsPath -Force
if (($backupsItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "backups_path_symlink_not_allowed"
}
$backupsRoot = (Resolve-Path -LiteralPath $backupsPath).Path
if (($BackupPath -split '[\\/]') -contains "..") {
    throw "parent_path_segment_not_allowed"
}
$candidate = if ([IO.Path]::IsPathRooted($BackupPath)) {
    [IO.Path]::GetFullPath($BackupPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $BackupPath))
}
$isWindows = $env:OS -eq "Windows_NT" -or [IO.Path]::DirectorySeparatorChar -eq '\'
$pathComparison = if ($isWindows) {
    [StringComparison]::OrdinalIgnoreCase
} else {
    [StringComparison]::Ordinal
}
$prefix = $backupsRoot + [IO.Path]::DirectorySeparatorChar
if (-not $candidate.StartsWith($prefix, $pathComparison)) {
    throw "backup_outside_repository_backups"
}

$relative = $candidate.Substring($prefix.Length)
$current = $backupsRoot
foreach ($part in ($relative -split '[\\/]')) {
    if ([string]::IsNullOrEmpty($part)) {
        continue
    }
    $current = Join-Path $current $part
    if (Test-Path -LiteralPath $current) {
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "backup_symlink_not_allowed"
        }
    }
}

$resolvedBackup = (Resolve-Path -LiteralPath $candidate).Path
if (-not $resolvedBackup.StartsWith($prefix, $pathComparison)) {
    throw "backup_outside_repository_backups"
}
$backupItem = Get-Item -LiteralPath $resolvedBackup -Force
if ($backupItem.PSIsContainer -or $backupItem.Length -le 0 -or $backupItem.Extension -ne ".dump") {
    throw "invalid_backup_file"
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

$checksumPath = "$resolvedBackup.sha256"
$manifestPath = "$resolvedBackup.manifest.json"
foreach ($sidecarPath in @($checksumPath, $manifestPath)) {
    if (-not (Test-Path -LiteralPath $sidecarPath -PathType Leaf)) {
        throw "backup_manifest_missing"
    }
    $sidecarItem = Get-Item -LiteralPath $sidecarPath -Force
    if (($sidecarItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $sidecarItem.Length -gt 4096) {
        throw "backup_manifest_invalid"
    }
}

$checksumText = [IO.File]::ReadAllText($checksumPath).Trim()
$checksumPattern = '^([0-9a-f]{64})  ' + [regex]::Escape($backupItem.Name) + '$'
if ($checksumText -notmatch $checksumPattern) {
    throw "backup_manifest_invalid"
}
$sidecarChecksum = $Matches[1]
try {
    $manifest = [IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
} catch {
    throw "backup_manifest_invalid"
}
$manifestKeys = @($manifest.PSObject.Properties.Name | Sort-Object)
if (
    ($manifestKeys -join ',') -ne 'archive,database,format,installation_id,sha256' -or
    $manifest.format -ne 2 -or
    $manifest.archive -cne $backupItem.Name -or
    $manifest.installation_id -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' -or
    $manifest.sha256 -notmatch '^[0-9a-f]{64}$'
) {
    throw "backup_manifest_invalid"
}
$actualChecksum = Get-Sha256Hex -Path $resolvedBackup
if ($sidecarChecksum -cne $manifest.sha256 -or $actualChecksum -cne $manifest.sha256) {
    throw "backup_checksum_mismatch"
}

$databaseName = Get-ContainerIdentifier -VariableName "POSTGRES_DB" -ErrorCode "invalid_POSTGRES_DB"
$databaseUser = Get-ContainerIdentifier -VariableName "POSTGRES_USER" -ErrorCode "invalid_POSTGRES_USER"
$installationId = Get-InstallationIdentifier
if ($manifest.database -cne $databaseName) {
    throw "backup_database_mismatch"
}
if ($manifest.installation_id -cne $installationId) {
    throw "backup_installation_mismatch"
}
Write-Output "Restoring database: $databaseName"

$containerTemp = "/tmp/diagnostic-restore-$([Guid]::NewGuid().ToString('N')).dump"
$containerSql = "/tmp/diagnostic-restore-$([Guid]::NewGuid().ToString('N')).sql"
$servicesToRestart = [Collections.Generic.List[string]]::new()
$restoreCompleted = $false
$primaryError = $null
$restartError = $null
$cleanupError = $null
$apiReady = $true
try {
    # docker compose cp preserves the archive without PowerShell text conversion.
    Invoke-DockerCommand -Arguments ($composePrefix + @("cp", $resolvedBackup, "db:$containerTemp"))
    Invoke-DockerCommand -Arguments ($composePrefix + @(
        "exec", "-T", "db", "pg_restore", "--list", $containerTemp
    ))
    Invoke-DockerCommand -Arguments ($composePrefix + @(
        "exec", "-T", "db", "sh", "-ceu",
        'printf ''DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public AUTHORIZATION "%s";\n'' "$1" > "$4"; pg_restore --clean --if-exists --no-owner --no-privileges --file=- "$3" >> "$4"; test -s "$4"',
        "sh", $databaseUser, $databaseName, $containerTemp, $containerSql
    ))
    $runningServices = @(
        (Invoke-DockerCapture -Arguments ($composePrefix + @(
            "ps", "--status", "running", "--services"
        ))) -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    )
    foreach ($service in @("api", "bot")) {
        if ($runningServices -contains $service) {
            $servicesToRestart.Add($service)
            Invoke-DockerCommand -Arguments ($composePrefix + @("stop", $service))
        }
    }
    Invoke-DockerCommand -Arguments ($composePrefix + @(
        "exec", "-T", "db", "sh", "-ceu",
        'psql --single-transaction --set=ON_ERROR_STOP=1 --username="$1" --dbname="$2" --file="$3"',
        "sh", $databaseUser, $databaseName, $containerSql
    ))
    $restoreCompleted = $true
} catch {
    $primaryError = $_
} finally {
    & docker @composePrefix exec -T db rm -f -- $containerTemp $containerSql | Out-Null
    if ($LASTEXITCODE -ne 0) { $cleanupError = "restore_temp_cleanup_failed" }
    foreach ($service in @("api", "bot")) {
        if (-not $servicesToRestart.Contains($service)) { continue }
        try {
            if ($service -eq "api") {
                Invoke-DockerCommand -Arguments ($composePrefix + @("up", "-d", "--wait", "api"))
                $apiReady = $true
            } else {
                if (-not $apiReady) { throw "api_not_ready_bot_not_restarted" }
                Invoke-DockerCommand -Arguments ($composePrefix + @("up", "-d", $service))
            }
        } catch {
            if ($service -eq "api") { $apiReady = $false }
            if ($null -eq $restartError) { $restartError = $_ }
        }
    }
}
if ($null -ne $primaryError) { throw $primaryError }
if ($null -ne $restartError) { throw $restartError }
if ($null -ne $cleanupError) { throw $cleanupError }
if ($restoreCompleted) {
    Write-Output "Restore completed and services restarted: $databaseName"
}

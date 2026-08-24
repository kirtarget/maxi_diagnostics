from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")


@pytest.mark.parametrize("script_name", ("backup_db.ps1", "restore_db.ps1"))
def test_backup_scripts_use_portable_sha256(script_name: str):
    script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")

    assert "Get-FileHash" not in script
    assert "function Get-Sha256Hex" in script
    assert "[Security.Cryptography.SHA256]::Create()" in script


def test_schema_migration_retires_legacy_unversioned_work():
    from diagnostic.db.schema import DDL

    assert "2026-08-11-retire-unversioned-attempts" in DDL
    assert "content_version=''" in DDL
    assert "status='superseded'" in DDL
    assert "pdf_status='abandoned'" in DDL


FAKE_DOCKER = r'''param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$DockerArguments
)
$line = ($DockerArguments -join "`t") + "`n"
[IO.File]::AppendAllText($env:DOCKER_LOG, $line)
$joined = $DockerArguments -join " "
if ($joined -match "printenv POSTGRES_DB") {
    Write-Output $env:FAKE_POSTGRES_DB
    exit 0
}
if ($joined -match "printenv POSTGRES_USER") {
    Write-Output $env:FAKE_POSTGRES_USER
    exit 0
}
if ($joined -match "printenv INSTALLATION_ID") {
    Write-Output $env:FAKE_INSTALLATION_ID
    exit 0
}
if ($joined -match "ps --status running --services") {
    Write-Output $env:FAKE_RUNNING_SERVICES
    exit 0
}
if ($env:FAKE_FAIL_MATCH -and $joined -match $env:FAKE_FAIL_MATCH) {
    exit 1
}
$cpIndex = [Array]::IndexOf($DockerArguments, "cp")
if ($cpIndex -ge 0) {
    $destination = $DockerArguments[$DockerArguments.Length - 1]
    if ($destination -notlike "db:*") {
        [IO.File]::WriteAllBytes($destination, [byte[]](1, 2, 3, 4))
    }
}
exit 0
'''


def _script_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("backup_db.ps1", "restore_db.ps1"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    (fake_bin / "docker.ps1").write_text(FAKE_DOCKER, encoding="utf-8")
    return repo, fake_bin


def _write_backup_set(
    repo: Path, *, payload: bytes = b"archive", database: str = "tenantdb",
    installation_id: str = "12345678-1234-4123-8123-123456789abc",
) -> Path:
    backup = repo / "backups" / "safe.dump"
    backup.parent.mkdir(exist_ok=True)
    backup.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    (backup.parent / f"{backup.name}.sha256").write_text(
        f"{checksum}  {backup.name}\n", encoding="utf-8"
    )
    (backup.parent / f"{backup.name}.manifest.json").write_text(
        json.dumps(
            {
                "format": 2,
                "archive": backup.name,
                "database": database,
                "installation_id": installation_id,
                "sha256": checksum,
            },
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )
    return backup


def _run_script(
    tmp_path: Path,
    script_name: str,
    *arguments: str,
    database: str = "tenantdb",
    user: str = "tenant_user",
    installation_id: str = "12345678-1234-4123-8123-123456789abc",
) -> tuple[subprocess.CompletedProcess[str], str, Path]:
    repo, fake_bin = _script_repo(tmp_path)
    log_path = tmp_path / "docker.log"
    env = os.environ.copy()
    env.pop("POSTGRES_DB", None)
    env.pop("POSTGRES_USER", None)
    env.update(
        {
            "PATH": str(fake_bin) + os.pathsep + env["PATH"],
            "DOCKER_LOG": str(log_path),
            "FAKE_POSTGRES_DB": database,
            "FAKE_POSTGRES_USER": user,
            "FAKE_INSTALLATION_ID": installation_id,
            "FAKE_RUNNING_SERVICES": "api\nbot",
            "FAKE_FAIL_MATCH": "",
        }
    )
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo / "scripts" / script_name),
            *arguments,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return result, log, repo


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_backup_uses_container_database_identity_without_host_environment(tmp_path: Path):
    result, log, repo = _run_script(tmp_path, "backup_db.ps1")

    assert result.returncode == 0, result.stderr
    assert "printenv\tPOSTGRES_DB" in log
    assert "printenv\tPOSTGRES_USER" in log
    assert "tenantdb" in log and "tenant_user" in log
    dumps = list((repo / "backups").glob("*.dump"))
    assert len(dumps) == 1 and dumps[0].read_bytes() == bytes((1, 2, 3, 4))
    checksum = hashlib.sha256(dumps[0].read_bytes()).hexdigest()
    assert (repo / "backups" / f"{dumps[0].name}.sha256").read_text(encoding="utf-8") == (
        f"{checksum}  {dumps[0].name}\n"
    )
    manifest = json.loads(
        (repo / "backups" / f"{dumps[0].name}.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest == {
        "format": 2,
        "archive": dumps[0].name,
        "database": "tenantdb",
        "installation_id": "12345678-1234-4123-8123-123456789abc",
        "sha256": checksum,
    }
    assert log.index("pg_restore\t--list") < log.index("cp\tdb:")


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_uses_container_database_identity_and_displays_only_database(tmp_path: Path):
    repo, _ = _script_repo(tmp_path)
    backup = _write_backup_set(repo)
    result, log, _ = _run_script(
        tmp_path,
        "restore_db.ps1",
        "-BackupPath",
        str(backup),
        "-ConfirmRestore",
    )

    assert result.returncode == 0, result.stderr
    assert "Restoring database: tenantdb" in result.stdout
    assert "tenant_user" not in result.stdout
    assert "printenv\tPOSTGRES_DB" in log
    assert "printenv\tPOSTGRES_USER" in log
    assert "tenantdb" in log and "tenant_user" in log
    assert "pg_restore" in log
    assert "stop\tapi" in log
    assert "stop\tbot" in log
    assert "up\t-d\t--wait\tapi" in log
    assert "up\t-d\tbot" in log
    assert log.index("pg_restore\t--list") < log.index("stop\tapi")
    restore_command = "sh\t-ceu\tpsql --single-transaction --set=ON_ERROR_STOP=1"
    assert log.index("stop\tbot") < log.index(restore_command)
    assert log.index(restore_command) < log.index("up\t-d\t--wait\tapi")


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_preserves_intentionally_stopped_bot(tmp_path: Path):
    repo, fake_bin = _script_repo(tmp_path)
    backup = _write_backup_set(repo)
    log_path = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update({
        "PATH": str(fake_bin) + os.pathsep + env["PATH"],
        "DOCKER_LOG": str(log_path),
        "FAKE_POSTGRES_DB": "tenantdb",
        "FAKE_POSTGRES_USER": "tenant_user",
        "FAKE_INSTALLATION_ID": "12345678-1234-4123-8123-123456789abc",
        "FAKE_RUNNING_SERVICES": "api",
        "FAKE_FAIL_MATCH": "",
    })
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(repo / "scripts/restore_db.ps1"), "-BackupPath", str(backup),
         "-ConfirmRestore"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    log = log_path.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert "stop\tapi" in log and "up\t-d\t--wait\tapi" in log
    assert "stop\tbot" not in log and "up\t-d\tbot" not in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_recovers_already_stopped_service_after_partial_stop_failure(tmp_path: Path):
    repo, fake_bin = _script_repo(tmp_path)
    backup = _write_backup_set(repo)
    log_path = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update({
        "PATH": str(fake_bin) + os.pathsep + env["PATH"],
        "DOCKER_LOG": str(log_path),
        "FAKE_POSTGRES_DB": "tenantdb",
        "FAKE_POSTGRES_USER": "tenant_user",
        "FAKE_INSTALLATION_ID": "12345678-1234-4123-8123-123456789abc",
        "FAKE_RUNNING_SERVICES": "api\nbot",
        "FAKE_FAIL_MATCH": "stop bot",
    })
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(repo / "scripts/restore_db.ps1"), "-BackupPath", str(backup),
         "-ConfirmRestore"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    log = log_path.read_text(encoding="utf-8")

    assert result.returncode != 0
    assert "stop\tapi" in log and "stop\tbot" in log
    assert "up\t-d\t--wait\tapi" in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_rejects_explicit_parent_segment_before_resolution(tmp_path: Path):
    repo, fake_bin = _script_repo(tmp_path)
    backup = repo / "backups" / "safe.dump"
    backup.parent.mkdir()
    backup.write_bytes(b"archive")
    log_path = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": str(fake_bin) + os.pathsep + env["PATH"],
            "DOCKER_LOG": str(log_path),
            "FAKE_POSTGRES_DB": "tenantdb",
            "FAKE_POSTGRES_USER": "tenant_user",
            "FAKE_INSTALLATION_ID": "12345678-1234-4123-8123-123456789abc",
        }
    )
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo / "scripts" / "restore_db.ps1"),
            "-BackupPath",
            "backups\\..\\backups\\safe.dump",
            "-ConfirmRestore",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "parent_path_segment_not_allowed" in result.stderr
    assert not log_path.exists()


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_rejects_unsafe_container_database_identifier(tmp_path: Path):
    repo, _ = _script_repo(tmp_path)
    backup = _write_backup_set(repo)
    result, log, _ = _run_script(
        tmp_path,
        "restore_db.ps1",
        "-BackupPath",
        str(backup),
        "-ConfirmRestore",
        database="bad database",
    )

    assert result.returncode != 0
    assert "invalid_POSTGRES_DB" in result.stderr
    assert "pg_restore" not in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_rejects_checksum_mismatch_before_stopping_writers(tmp_path: Path):
    repo, _ = _script_repo(tmp_path)
    backup = _write_backup_set(repo)
    backup.write_bytes(b"tampered")

    result, log, _ = _run_script(
        tmp_path, "restore_db.ps1", "-BackupPath", str(backup), "-ConfirmRestore"
    )

    assert result.returncode != 0
    assert "backup_checksum_mismatch" in result.stderr
    assert "\tstop\t" not in log and "pg_restore\t--list" not in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_rejects_backup_for_another_database_before_stopping_writers(tmp_path: Path):
    repo, _ = _script_repo(tmp_path)
    backup = _write_backup_set(repo, database="otherdb")

    result, log, _ = _run_script(
        tmp_path, "restore_db.ps1", "-BackupPath", str(backup), "-ConfirmRestore"
    )

    assert result.returncode != 0
    assert "backup_database_mismatch" in result.stderr
    assert "\tstop\t" not in log and "pg_restore\t--list" not in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_rejects_backup_for_another_installation_before_stopping_writers(tmp_path: Path):
    repo, _ = _script_repo(tmp_path)
    backup = _write_backup_set(
        repo, installation_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    )

    result, log, _ = _run_script(
        tmp_path, "restore_db.ps1", "-BackupPath", str(backup), "-ConfirmRestore"
    )

    assert result.returncode != 0
    assert "backup_installation_mismatch" in result.stderr
    assert "\tstop\t" not in log and "pg_restore\t--list" not in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_recreates_public_schema_before_loading_archive(tmp_path: Path):
    repo, _ = _script_repo(tmp_path)
    backup = _write_backup_set(repo)

    result, log, _ = _run_script(
        tmp_path, "restore_db.ps1", "-BackupPath", str(backup), "-ConfirmRestore"
    )

    assert result.returncode == 0, result.stderr
    assert "DROP SCHEMA IF EXISTS public CASCADE" in log
    assert "CREATE SCHEMA public AUTHORIZATION" in log
    assert "pg_restore --single-transaction --clean" not in log
    assert "psql --single-transaction --set=ON_ERROR_STOP=1" in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_backup_rejects_template_installation_identity(tmp_path: Path):
    result, log, _ = _run_script(
        tmp_path,
        "backup_db.ps1",
        installation_id="00000000-0000-4000-8000-000000000000",
    )

    assert result.returncode != 0
    assert "invalid_INSTALLATION_ID" in result.stderr
    assert "pg_dump" not in log


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is unavailable")
def test_restore_does_not_start_bot_when_api_health_restart_fails(tmp_path: Path):
    repo, fake_bin = _script_repo(tmp_path)
    backup = _write_backup_set(repo)
    log_path = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update({
        "PATH": str(fake_bin) + os.pathsep + env["PATH"],
        "DOCKER_LOG": str(log_path),
        "FAKE_POSTGRES_DB": "tenantdb",
        "FAKE_POSTGRES_USER": "tenant_user",
        "FAKE_INSTALLATION_ID": "12345678-1234-4123-8123-123456789abc",
        "FAKE_RUNNING_SERVICES": "api\nbot",
        "FAKE_FAIL_MATCH": "up -d --wait api",
    })

    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(repo / "scripts/restore_db.ps1"), "-BackupPath", str(backup),
         "-ConfirmRestore"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    log = log_path.read_text(encoding="utf-8")

    assert result.returncode != 0
    assert "up\t-d\t--wait\tapi" in log
    assert "up\t-d\tbot" not in log

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_readme_documents_the_exact_safe_first_run_sequence():
    text = read("README.md")
    ordered = [
        "clean reviewed revision", "Do not run `scripts/init_school.py`",
        "school/brand.json", "school/links.json", "school/diagnostics",
        "scripts/validate_school.py", "scripts/check_brand_isolation.py",
        ".env.example", "BotFather", "docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml up -d --build",
    ]
    positions = [text.index(value) for value in ordered]
    assert positions == sorted(positions)
    assert "Do not commit `.env`" in text
    assert text.index("Creating a separate white-label repository") < text.index("Use this template")
    assert "Do not use `--force` to repurpose live MAXIMUM public configuration." in text


def test_operator_documents_cover_deploy_operations_and_handoff_contracts():
    deployment = read("docs/DEPLOYMENT.md")
    operations = read("docs/OPERATIONS.md")
    handoff = read("docs/HANDOFF.md")

    for value in ("DNS", "HTTPS", "Nginx", "BotFather", "Mini App", "/healthz", "127.0.0.1:18082"):
        assert value in deployment
    assert "APPLICATION_SECRET" in deployment
    assert "secrets.token_urlsafe(32)" in deployment
    assert "docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml config --quiet" in deployment
    assert "docker compose config\n" not in deployment
    assert "Do not run\n`scripts/init_school.py` or use `--force` during deployment." in deployment
    assert "/.well-known/acme-challenge/" in deployment
    for value in (
        "docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml logs", "one polling", "scripts/backup_db.ps1",
        "-ConfirmRestore", "rollback", "abandoned", "docker compose down",
    ):
        assert value.casefold() in operations.casefold()
    assert "docker compose down -v" not in operations
    assert "Local automated checks prove" in operations
    assert "protected\nstorage is reachable" in operations
    for value in (
        "repository", "domain", "DNS", "server", "BotFather", "protected channel",
        "admin", "restore drill", "remove developer access",
    ):
        assert value.casefold() in handoff.casefold()
    assert "automatic BotFather transfer" not in handoff


def test_content_format_has_complete_server_only_examples():
    content = read("docs/CONTENT_FORMAT.md")

    for question_type in ("single", "multiple", "input", "matching"):
        assert f'"type": "{question_type}"' in content
    assert "Numeric input" in content
    assert '"selection_limit"' in content
    assert '"items"' in content
    assert '"correct"' in content
    assert "server-only" in content.casefold()
    assert "assets/questions/" in content
    assert "## Text input" not in content
    assert '"correct": ["3.5"]' in content
    assert "42" in content and "3.5" in content
    assert "comma or dot" in content
    assert "arbitrary text" in content.casefold() and "not" in content.casefold()


def test_content_format_documents_the_post_completion_review_boundary():
    content = " ".join(read("docs/CONTENT_FORMAT.md").split())

    assert "`explanation`, `learning_material_text` and `learning_material_url` are optional" in content
    assert "`learning_material_text` is at most 1,200 characters" in content
    assert "excluded from bootstrap and public assets" in content
    assert "after an authenticated completed attempt" in content.casefold()
    assert "display-only `expected_answer` and resolved guidance" in content
    assert "does not fabricate a general algorithm" in content
    assert "without `review_snapshot` remain legacy reports" in content


def test_nginx_example_is_fixed_host_same_origin_and_has_no_open_proxy():
    config = read("deploy/nginx/diagnostic.conf.example")

    assert "server_name maxi.kirtarget.ru;" in config
    assert "return 301 https://maxi.kirtarget.ru$request_uri;" in config
    assert "proxy_pass http://127.0.0.1:18080" in config
    assert "proxy_pass http://127.0.0.1:13000" in config
    for route in ("/api/", "/admin/", "/admin/static/", "/healthz"):
        assert route in config
    assert config.count("include proxy_params;") == 6
    assert "proxy_set_header Host" not in config
    assert "Strict-Transport-Security \"max-age=31536000\" always" in config
    assert "limit_req_zone $binary_remote_addr zone=diagnostic_api:" in config
    assert "limit_req_zone $binary_remote_addr zone=diagnostic_admin:" in config
    assert "limit_req zone=diagnostic_api" in config
    assert "limit_req zone=diagnostic_admin" in config
    assert "limit_req_status 429;" in config
    health = config.split("location = /healthz {", 1)[1].split("}", 1)[0]
    assert "limit_req zone=diagnostic_api" in health
    assert "proxy_set_header Upgrade $http_upgrade" in config
    assert "proxy_read_timeout" in config
    assert "proxy_pass $" not in config


def test_production_configuration_has_one_canonical_host_and_private_ports():
    paths = (
        ".env.example", "README.md", "docker-compose.yml",
        "deploy/docker-compose.production.yml", "deploy/nginx/diagnostic.conf.example",
        "deploy/nginx/maxi.kirtarget.ru.conf", "deploy/nginx/maxi.kirtarget.ru.http.conf",
        "docs/DEPLOYMENT.md", "docs/OPERATIONS.md",
    )
    configuration = "\n".join(read(path) for path in paths)

    assert "maximumtest.ru" not in configuration
    assert "https://maxi.kirtarget.ru" in configuration
    assert 'BOT_POLLING_ENABLED=true' in read(".env.example")
    assert '"127.0.0.1:18082:8080"' in read("deploy/docker-compose.production.yml")
    assert '"127.0.0.1:13002:3000"' in read("deploy/docker-compose.production.yml")
    for path in (
        "deploy/nginx/diagnostic.conf.example", "deploy/nginx/maxi.kirtarget.ru.conf",
        "deploy/nginx/maxi.kirtarget.ru.http.conf",
    ):
        assert "server_name maxi.kirtarget.ru;" in read(path)


def test_backup_and_restore_are_binary_safe_guarded_and_contained():
    backup = read("scripts/backup_db.ps1")
    restore = read("scripts/restore_db.ps1")

    assert "pg_dump" in backup and "--format=custom" in backup
    assert "docker compose cp" in backup
    assert "finally" in backup and "backups" in backup
    assert "--project-directory" in backup
    assert "[switch]$ConfirmRestore" in restore
    assert "Resolve-Path" in restore and "ReparsePoint" in restore
    assert "pg_restore" in restore
    for option in ("--single-transaction", "--clean", "--if-exists"):
        assert option in restore
    assert "docker compose cp" in restore and "finally" in restore
    assert "--project-directory" in restore
    assert "GetRelativePath" not in restore
    assert "$env:POSTGRES_DB" not in restore
    assert "printenv" in restore and "POSTGRES_DB" in restore
    assert "[StringComparison]::OrdinalIgnoreCase" in restore
    assert "[StringComparison]::Ordinal" in restore
    assert "Windows_NT" in restore
    assert "parent_path_segment_not_allowed" in restore
    assert "down -v" not in (backup + restore)
    assert ">" not in backup
    assert "pg_restore --clean --if-exists --no-owner --no-privileges --file=-" in restore
    assert "psql --single-transaction --set=ON_ERROR_STOP=1" in restore


def test_operations_documents_platform_correct_powershell_invocations():
    operations = read("docs/OPERATIONS.md")

    assert "Windows PowerShell 5.1" in operations
    assert "powershell -File scripts/backup_db.ps1" in operations
    assert "powershell -File scripts/restore_db.ps1" in operations
    assert "Linux and macOS require PowerShell 7" in operations
    assert "pwsh -File scripts/backup_db.ps1" in operations
    assert "pwsh -File scripts/restore_db.ps1" in operations


def test_ci_matches_local_gates_and_uses_only_safe_test_services():
    workflow = yaml.safe_load(read(".github/workflows/ci.yml"))
    rendered = json.dumps(workflow, ensure_ascii=False)

    assert "postgres:16-alpine" in rendered
    assert "actions/setup-python" in rendered and "3.11" in rendered
    assert "actions/setup-node" in rendered and "22" in rendered
    for command in (
        "pip install --no-deps -r requirements-dev-lock.txt", "python scripts/validate_school.py",
        "python scripts/check_brand_isolation.py --history", "python -m pytest -q",
        "npm ci", "npm run test:unit", "npm run build", "npm test",
        "docker compose config --quiet", "docker compose build",
    ):
        assert command in rendered
    assert "TEST_DATABASE_URL" in rendered

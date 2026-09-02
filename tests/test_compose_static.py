from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_compose_has_only_transferable_services_and_project_volume():
    compose = yaml.safe_load(read("docker-compose.yml"))

    assert set(compose["services"]) == {"db", "api", "bot", "miniapp"}
    rendered = json.dumps(compose, ensure_ascii=False).casefold()
    assert "container_name" not in rendered
    assert "bind" not in rendered
    assert "../" not in rendered
    for term in json.loads(read("scripts/source_brand_terms.json"))["terms"]:
        assert set(term) == {"sha256", "length", "rolling64"}
    db_image = compose["services"]["db"]["image"]
    assert db_image.startswith("postgres:16-alpine@sha256:")
    assert len(db_image.rsplit("@sha256:", 1)[1]) == 64
    assert compose["services"]["db"]["volumes"] == ["postgres_data:/var/lib/postgresql/data"]
    assert set(compose["volumes"]) == {"postgres_data"}
    assert "${IMAGE_NAMESPACE:?" in compose["services"]["api"]["image"]
    assert "${IMAGE_NAMESPACE:?" in compose["services"]["miniapp"]["image"]
    assert compose["services"]["api"]["image"] != compose["services"]["miniapp"]["image"]


def test_compose_has_safe_commands_dependencies_ports_and_required_environment():
    services = yaml.safe_load(read("docker-compose.yml"))["services"]

    assert services["api"]["command"] == [
        "python", "-m", "uvicorn", "diagnostic.api.main:create_default_app", "--factory",
        "--host", "0.0.0.0", "--port", "8080",
    ]
    assert services["bot"]["command"] == ["python", "-m", "diagnostic.bot.main"]
    assert services["bot"]["healthcheck"] == {"disable": True}
    assert services["api"]["ports"] == ["127.0.0.1:18080:8080"]
    assert services["miniapp"]["ports"] == ["127.0.0.1:13000:3000"]
    assert "ports" not in services["db"] and "ports" not in services["bot"]
    for name in ("db", "api", "bot", "miniapp"):
        assert services[name]["restart"] == "unless-stopped"
        assert services[name]["logging"] == {
            "driver": "json-file",
            "options": {"max-size": "10m", "max-file": "5"},
        }
    assert services["api"]["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert services["bot"]["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert "bot" not in services["miniapp"].get("depends_on", {})
    assert "ADMIN_USERNAME" in services["api"]["environment"]
    assert "ADMIN_PASSWORD" in services["api"]["environment"]
    assert "ADMIN_USERNAME" not in services["bot"]["environment"]
    assert "ADMIN_PASSWORD" not in services["bot"]["environment"]
    db_health = " ".join(services["db"]["healthcheck"]["test"])
    assert "00000000-0000-4000-8000-000000000000" in db_health
    assert "INSTALLATION_ID" in db_health
    rendered = read("docker-compose.yml")
    for variable in (
        "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DATABASE_URL",
        "IMAGE_NAMESPACE", "INSTALLATION_ID",
    ):
        assert f"${{{variable}:?" in rendered


def test_backend_and_miniapp_images_are_reproducible_minimal_and_non_root():
    backend = read("backend/Dockerfile")
    miniapp = read("miniapp/Dockerfile")
    requirements = {
        line.strip() for line in read("requirements.txt").splitlines()
        if line.strip() and not line.startswith("#")
    }
    runtime_lock = {
        line.strip() for line in read("requirements-lock.txt").splitlines()
        if line.strip() and not line.startswith("#")
    }
    dev_lock = {
        line.strip() for line in read("requirements-dev-lock.txt").splitlines()
        if line.strip() and not line.startswith("#")
    }
    build_lock = {
        line.strip() for line in read("requirements-build-lock.txt").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert backend.startswith("FROM python:3.11-slim@sha256:")
    assert "COPY requirements-lock.txt" in backend
    assert "COPY requirements-build-lock.txt" in backend
    assert "--no-deps -r /app/requirements-build-lock.txt" in backend
    assert "--no-build-isolation" in backend
    assert "pip wheel" in backend and "/app/wheelhouse" in backend
    assert "--no-index --find-links=/app/wheelhouse --no-deps" in backend
    assert "AS python-dependencies" in backend
    assert "libcairo2-dev" in backend and "pkg-config" in backend and "build-essential" in backend
    assert "libcairo2" in backend
    assert "COPY --from=python-dependencies /opt/venv /opt/venv" in backend
    assert "collect_python_licenses.py" in backend
    assert "COPY --from=python-dependencies /app/licenses/python-runtime" in backend
    assert "third_party_licenses/python" in backend
    assert "/app/licenses/system-runtime" in backend
    assert "COPY backend" in backend and "COPY school" in backend
    assert "PYTHONPATH=/app/backend" in backend
    assert "USER diagnostic" in backend
    assert "EXPOSE 8080" in backend
    assert "urllib.request" in backend and "127.0.0.1:8080/healthz" in backend
    assert requirements and all("==" in line for line in requirements)
    assert requirements <= runtime_lock <= dev_lock
    assert build_lock == {
        "meson-python==0.20.0",
        "meson==1.11.2",
        "ninja==1.13.0",
        "packaging==26.3",
        "pyproject-metadata==0.12.1",
        "wheel==0.45.1",
    }

    assert "FROM node:22-alpine@sha256:" in miniapp
    assert "npm ci" in miniapp and "npm run build" in miniapp
    assert "COPY school/brand.json school/links.json /app/school/" in miniapp
    assert "COPY school/assets" in miniapp
    assert ".next/standalone" in miniapp
    assert "USER node" in miniapp and "EXPOSE 3000" in miniapp
    assert "127.0.0.1:3000" in miniapp


def test_dockerignore_keeps_runtime_inputs_and_excludes_local_or_secret_material():
    patterns = set(read(".dockerignore").splitlines())

    for pattern in (
        ".git", ".env", ".env.*", "!.env.example", "**/.env", "**/.env.*",
        "**/service_account*.json", "school/private/", ".venv", ".venv312",
        "**/__pycache__", "**/node_modules", "**/.next", "**/.pytest_cache",
        "**/logs", "**/*.log", "**/dist", "**/build", "**/output", "**/tmp",
        "**/cache", "**/backups", "**/*.dump", "**/*.bak", "**/*.backup",
        "**/test-results", "**/playwright-report",
    ):
        assert pattern in patterns
    for required in (
        "backend", "backend/diagnostic", "backend/diagnostic/reporting/fonts",
        "school", "school/assets", "miniapp", "miniapp/app",
    ):
        assert required not in patterns


def test_api_factory_owns_database_lifecycle_for_the_production_command():
    source = read("backend/diagnostic/api/main.py")

    assert "asynccontextmanager" in source
    assert "await init_db(settings.database_url, school)" in source
    assert "await close_db()" in source


def test_ci_supplies_stable_test_application_secret_without_printing_compose_secrets():
    workflow = read(".github/workflows/ci.yml")

    assert "runs-on: ubuntu-24.04" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "APPLICATION_SECRET:" in workflow
    assert "IMAGE_NAMESPACE:" in workflow
    assert "INSTALLATION_ID:" in workflow
    assert "python -m pip install --no-deps -r requirements-dev-lock.txt" in workflow
    assert workflow.index("libcairo2-dev") < workflow.index("pip install --no-deps")
    assert "python -m pip install -r requirements-dev.txt" not in workflow
    assert "docker compose config --quiet" in workflow
    assert "run: docker compose config\n" not in workflow
    for action in ("actions/checkout", "actions/setup-python", "actions/setup-node"):
        lines = [line.strip() for line in workflow.splitlines() if f"uses: {action}@" in line]
        assert len(lines) == 1
        revision = lines[0].split("@", 1)[1].split()[0]
        assert len(revision) == 40 and all(character in "0123456789abcdef" for character in revision)
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 0" in workflow


def test_nginx_limits_are_classroom_nat_safe_and_admin_supports_dashboard_fanout():
    nginx = read("deploy/nginx/diagnostic.conf.example")

    assert "zone=diagnostic_api:10m rate=30r/s" in nginx
    assert "limit_req zone=diagnostic_api burst=200 nodelay" in nginx
    assert "zone=diagnostic_admin:10m rate=30r/m" in nginx
    assert "limit_req zone=diagnostic_admin burst=30 nodelay" in nginx
    rate_location = nginx.split("location @diagnostic_rate_limited", 1)[1].split("}", 1)[0]
    assert "Strict-Transport-Security" in rate_location
    assert 'add_header Retry-After "1" always' in rate_location


def test_miniapp_runtime_retains_direct_production_dependency_licenses():
    dockerfile = read("miniapp/Dockerfile")
    expected = {
        "third_party_licenses/node/next-16.3.0.txt": "Copyright (c) 2025 Vercel, Inc.",
        "third_party_licenses/node/react-19.2.6.txt": "Copyright (c) Meta Platforms, Inc. and affiliates.",
        "third_party_licenses/node/react-dom-19.2.6.txt": "Copyright (c) Meta Platforms, Inc. and affiliates.",
    }

    assert "COPY --chown=node:node LICENSE THIRD_PARTY_NOTICES.md third_party_licenses /app/licenses/" in dockerfile
    assert "node scripts/collect-production-licenses.mjs" in dockerfile
    assert "THIRD_PARTY_NODE_LICENSES.txt" in dockerfile
    assert "COPY --chown=node:node --from=licenses /app/licenses /app/licenses/node-runtime" in dockerfile
    collector = read("miniapp/scripts/collect-production-licenses.mjs")
    assert "package-lock.json" in collector
    assert 'relativePackage.startsWith("node_modules/@img/sharp-libvips-")' in collector
    assert 'path.join(packageDirectory, "README.md")' in collector
    assert "license_file_missing" in collector
    for relative, copyright_line in expected.items():
        text = read(relative)
        assert copyright_line in text
        assert "Permission is hereby granted" in text


def test_backend_runtime_license_inventory_is_fail_closed_with_audited_fallbacks():
    collector = read("scripts/collect_python_licenses.py")
    dockerfile = read("backend/Dockerfile")
    expected = {
        "third_party_licenses/python/rlpycairo-0.4.0-BSD.txt": "Copyright (c) 2000-2022, ReportLab Inc.",
        "third_party_licenses/python/webencodings-0.5.1-BSD.txt": "Copyright (c) 2012 by Simon Sapin.",
        "third_party_licenses/python/pycairo-1.29.1-provenance.txt": "LGPL-2.1-only OR MPL-1.1",
    }

    assert "python_license_file_missing" in collector
    assert 'Path("/usr/share/common-licenses/LGPL-2.1")' in collector
    assert "No license text was packaged" not in collector
    assert "dpkg-query" in dockerfile and "/usr/share/doc/${base}/copyright" in dockerfile
    for relative, marker in expected.items():
        assert marker in read(relative)

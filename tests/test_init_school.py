from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "init_school.py"


def load_tool():
    assert SCRIPT.is_file(), "school initializer is missing"
    spec = importlib.util.spec_from_file_location("task9_init_school", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_root(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "tests/fixtures/sample-school", tmp_path / "school")
    shutil.copy2(ROOT / ".env.example", tmp_path / ".env.example")
    return tmp_path


def arguments(**overrides: str) -> list[str]:
    values = {
        "name": "Новая школа",
        "short_name": "Школа",
        "school_id": "new-school",
        "domain": "diagnostic.new-school.example",
        "bot_username": "new_school_bot",
        "primary_color": "#123456",
        "accent_color": "#ABCDEF",
    }
    values.update(overrides)
    result: list[str] = []
    for key, value in values.items():
        result.extend((f"--{key.replace('_', '-')}", value))
    return result


def test_initializer_writes_valid_non_secret_configuration_and_preserves_content(
    tmp_path: Path, capsys
):
    root = sample_root(tmp_path)
    content_before = {
        path.relative_to(root): path.read_bytes()
        for directory in (root / "school/diagnostics", root / "school/assets")
        for path in directory.rglob("*")
        if path.is_file()
    }
    interface_before = json.loads((root / "school/brand.json").read_text(encoding="utf-8"))["interface"]

    result = load_tool().main(arguments(), root=root)

    assert result == 0
    assert capsys.readouterr().out == "OK initialized school=new-school domain=diagnostic.new-school.example\n"
    env_text = (root / ".env.example").read_text(encoding="utf-8")
    installation_line = next(
        line for line in env_text.splitlines() if line.startswith("INSTALLATION_ID=")
    )
    assert re.fullmatch(
        r"INSTALLATION_ID=[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        installation_line,
    )
    assert installation_line != "INSTALLATION_ID=00000000-0000-4000-8000-000000000000"
    assert env_text.replace(f"{installation_line}\n", "") == (
        "POSTGRES_DB=diagnostic\n"
        "IMAGE_NAMESPACE=new-school-diagnostic\n"
        "POSTGRES_USER=diagnostic\n"
        "POSTGRES_PASSWORD=\n"
        "DATABASE_URL=\n"
        "BOT_TOKEN=\n"
        "APPLICATION_SECRET=\n"
        "BOT_USERNAME=new_school_bot\n"
        "MINIAPP_URL=https://diagnostic.new-school.example\n"
        "MINIAPP_ORIGIN=https://diagnostic.new-school.example\n"
        "ADMIN_USERNAME=admin\n"
        "ADMIN_PASSWORD=\n"
        "ANALYTICS_WEBHOOK_URL=\n"
        "TIMEZONE=Europe/Moscow\n"
    )
    assert (root / ".env.example").read_bytes()[:3] != b"\xef\xbb\xbf"
    marker = root / "school/.initialized.json"
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "format": 1,
        "school_id": "new-school",
    }
    brand = json.loads((root / "school/brand.json").read_text(encoding="utf-8"))
    assert brand["name"] == "Новая школа"
    assert brand["interface"] == interface_before
    assert all(
        (root / relative).read_bytes() == payload
        for relative, payload in content_before.items()
    )
    school = load_school(root / "school")
    assert len(load_catalog(school).diagnostics) == 1


def test_initializer_refuses_real_brand_without_force_and_force_only_updates_config(
    tmp_path: Path, capsys
):
    root = sample_root(tmp_path)
    tool = load_tool()
    assert tool.main(arguments(), root=root) == 0
    capsys.readouterr()
    tracked_content = {
        path.relative_to(root): path.read_bytes()
        for path in (root / "school/diagnostics").rglob("*")
        if path.is_file()
    } | {
        path.relative_to(root): path.read_bytes()
        for path in (root / "school/assets").rglob("*")
        if path.is_file()
    }

    assert tool.main(arguments(name="Second name"), root=root) == 1
    assert capsys.readouterr().out == "ERROR school_already_initialized_use_force\n"
    assert json.loads((root / "school/brand.json").read_text(encoding="utf-8"))["name"] == "Новая школа"

    assert tool.main([*arguments(name="Second name"), "--force"], root=root) == 0
    capsys.readouterr()
    assert json.loads((root / "school/brand.json").read_text(encoding="utf-8"))["name"] == "Second name"
    assert all((root / relative).read_bytes() == content for relative, content in tracked_content.items())


def test_initializer_marker_prevents_repeat_when_school_id_matches_template(
    tmp_path: Path, capsys
):
    root = sample_root(tmp_path)
    tool = load_tool()
    template_id_arguments = arguments(school_id="demo-school")

    assert tool.main(template_id_arguments, root=root) == 0
    capsys.readouterr()
    assert (root / "school/.initialized.json").is_file()
    assert tool.main(template_id_arguments, root=root) == 1
    assert capsys.readouterr().out == "ERROR school_already_initialized_use_force\n"


def test_initializer_preserves_installation_identity_on_force(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    tool = load_tool()
    assert tool.main(arguments(), root=root) == 0
    capsys.readouterr()
    first = next(
        line for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.startswith("INSTALLATION_ID=")
    )

    assert tool.main([*arguments(name="Updated school"), "--force"], root=root) == 0
    capsys.readouterr()
    second = next(
        line for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.startswith("INSTALLATION_ID=")
    )

    assert second == first


def test_independent_initializations_receive_distinct_installation_ids(tmp_path: Path, capsys):
    tool = load_tool()
    roots = [sample_root(tmp_path / name) for name in ("first", "second")]
    identifiers = []
    for index, root in enumerate(roots):
        assert tool.main(arguments(school_id=f"school-{index}"), root=root) == 0
        capsys.readouterr()
        identifiers.append(
            next(
                line.split("=", 1)[1]
                for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
                if line.startswith("INSTALLATION_ID=")
            )
        )

    assert identifiers[0] != identifiers[1]


@pytest.mark.parametrize("config_name", ["brand.json", "links.json"])
def test_initializer_refuses_edited_unmarked_configuration(
    tmp_path: Path, capsys, config_name: str
):
    root = sample_root(tmp_path)
    path = root / "school" / config_name
    data = json.loads(path.read_text(encoding="utf-8"))
    data["unexpected_edit"] = True
    original = json.dumps(data, ensure_ascii=False).encode("utf-8")
    path.write_bytes(original)

    result = load_tool().main(arguments(), root=root)

    assert result == 1
    assert capsys.readouterr().out == "ERROR school_not_pristine_use_force\n"
    assert path.read_bytes() == original
    assert not (root / "school/.initialized.json").exists()


@pytest.mark.parametrize("failure_at", [2, 3])
def test_initializer_rolls_back_all_outputs_when_replace_fails(
    tmp_path: Path, capsys, monkeypatch, failure_at: int
):
    root = sample_root(tmp_path)
    tool = load_tool()
    targets = [
        root / ".env.example",
        root / "school/brand.json",
        root / "school/links.json",
        root / "school/.initialized.json",
    ]
    originals = {path: path.read_bytes() if path.exists() else None for path in targets}
    real_replace = tool._replace
    calls = 0

    def fail_once(source, destination):
        nonlocal calls
        calls += 1
        if calls == failure_at:
            raise OSError("injected replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(tool, "_replace", fail_once)

    assert tool.main(arguments(), root=root) == 1
    assert capsys.readouterr().out == "ERROR initialization_write_failed\n"
    assert all(
        (path.read_bytes() if path.exists() else None) == original
        for path, original in originals.items()
    )
    monkeypatch.setattr(tool, "_replace", real_replace)
    assert tool.main(arguments(), root=root) == 0
    capsys.readouterr()
    assert (root / "school/.initialized.json").is_file()


def test_initializer_rejects_dangling_marker_symlink_before_exists_check(
    tmp_path: Path, capsys, monkeypatch
):
    root = sample_root(tmp_path)
    tool = load_tool()
    marker = root / "school/.initialized.json"
    try:
        marker.symlink_to(root / "missing-marker-target")
    except OSError:
        original = Path.is_symlink
        monkeypatch.setattr(
            Path, "is_symlink", lambda path: True if path == marker else original(path)
        )

    result = tool.main(arguments(), root=root)

    assert result == 1
    assert capsys.readouterr().out == "ERROR unsafe_config_path\n"


@pytest.mark.parametrize(
    "domain",
    [
        "https://school.example",
        "user@school.example",
        "school.example:8443",
        "school.example/path",
        "school.example?query=1",
        "school.example#fragment",
        "example..com",
        "999.999.999.999",
        "0x7f000001",
        "１２７.０.０.１",
    ],
)
def test_initializer_rejects_non_hostname_or_malformed_domain(
    tmp_path: Path, capsys, domain: str
):
    result = load_tool().main(arguments(domain=domain), root=sample_root(tmp_path))

    assert result == 1
    assert capsys.readouterr().out == "ERROR invalid_domain\n"


@pytest.mark.parametrize(
    "overrides",
    [
        {"school_id": "Bad School"},
        {"bot_username": "short"},
        {"bot_username": "not-a-bot"},
        {"bot_username": "changed_for_me"},
        {"primary_color": "red"},
        {"accent_color": "#12345G"},
        {"name": "x" * 129},
        {"short_name": "x" * 65},
    ],
)
def test_initializer_rejects_invalid_public_brand_values(
    tmp_path: Path, capsys, overrides: dict[str, str]
):
    result = load_tool().main(arguments(**overrides), root=sample_root(tmp_path))

    assert result == 1
    output = capsys.readouterr().out
    assert output.startswith("ERROR invalid_")
    assert output.count("\n") == 1


def test_initializer_rejects_missing_and_symlink_roots(tmp_path: Path, capsys):
    tool = load_tool()
    assert tool.main(arguments(), root=tmp_path / "missing") == 1
    assert capsys.readouterr().out == "ERROR root_not_found\n"
    real = sample_root(tmp_path / "real")
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    assert tool.main(arguments(), root=link) == 1
    assert capsys.readouterr().out == "ERROR root_symlink_not_allowed\n"


def test_initializer_cli_has_no_secret_options_and_runs_from_arbitrary_cwd(tmp_path: Path):
    assert SCRIPT.is_file(), "school initializer is missing"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert "--force" in result.stdout
    for forbidden in ("--token", "--bot-token", "--password", "--admin-password", "--secret"):
        assert forbidden not in result.stdout.lower()

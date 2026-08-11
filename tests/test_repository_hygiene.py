from pathlib import Path
import fnmatch
import subprocess

from dotenv import dotenv_values


SECRET_PATTERNS = (
    ".env", ".env.*", ".npmrc", ".pypirc", ".netrc", ".pgpass",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "*.dump", "*.backup", "*.bak", "service_account*.json",
    "credentials*.json", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
)


def _secret_path(relative: str) -> bool:
    normalized = relative.replace("\\", "/").casefold()
    name = normalized.rsplit("/", 1)[-1]
    if name == ".env.example":
        return False
    return "school/private/" in f"{normalized}/" or any(
        fnmatch.fnmatch(name, pattern) for pattern in SECRET_PATTERNS
    )


def test_repository_has_no_secret_files_or_symlinks():
    root = Path(__file__).resolve().parents[1]
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True,
            encoding="utf-8", check=True,
        )
        tracked = result.stdout.splitlines()
        modes = subprocess.run(
            ["git", "ls-files", "-s"], cwd=root, capture_output=True, text=True,
            encoding="utf-8", check=True,
        ).stdout.splitlines()
        assert not any(line.startswith("120000 ") for line in modes)
    else:
        tracked = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*") if path.is_file() or path.is_symlink()
        ]
        assert not any(path.is_symlink() for path in root.rglob("*"))
    assert not [relative for relative in tracked if _secret_path(relative)]

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        ".env.*", "!.env.example", "*.key", "*.p12", "*.pfx", "*.jks",
        "*.keystore", "*.dump", "*.backup", "*.bak", ".npmrc", ".pypirc",
        ".netrc", ".pgpass", "credentials*.json",
    ):
        assert pattern in gitignore


def test_sample_environment_keeps_secret_values_empty():
    root = Path(__file__).resolve().parents[1]
    values = dotenv_values(root / ".env.example")

    assert values["DATABASE_URL"] == ""
    assert values["BOT_TOKEN"] == ""
    assert values["APPLICATION_SECRET"] == ""
    assert values["ADMIN_PASSWORD"] == ""

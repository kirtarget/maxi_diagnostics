"""Collect installed Python distribution license metadata and packaged notices."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
import re
import sys


NOTICE_NAME = re.compile(r"^(license|licence|copying|notice)(\..*)?$", re.IGNORECASE)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUDITED_FALLBACKS: dict[tuple[str, str], tuple[Path, ...]] = {
    ("pycairo", "1.29.1"): (
        REPOSITORY_ROOT / "third_party_licenses/python/pycairo-1.29.1-provenance.txt",
        Path("/usr/share/common-licenses/LGPL-2.1"),
    ),
    ("rlpycairo", "0.4.0"): (
        REPOSITORY_ROOT / "third_party_licenses/python/rlpycairo-0.4.0-BSD.txt",
    ),
    ("webencodings", "0.5.1"): (
        REPOSITORY_ROOT / "third_party_licenses/python/webencodings-0.5.1-BSD.txt",
    ),
}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: collect_python_licenses.py OUTPUT_DIRECTORY")
    output_directory = Path(sys.argv[1]).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / "THIRD_PARTY_PYTHON_LICENSES.txt"
    sections = [
        "Installed Python dependency licenses",
        "Generated from the exact installed distribution metadata.",
        "",
    ]
    distributions = sorted(
        metadata.distributions(),
        key=lambda item: (item.metadata.get("Name", "").casefold(), item.version),
    )
    if not distributions:
        raise RuntimeError("python_license_inventory_empty")
    for distribution in distributions:
        name = distribution.metadata.get("Name") or "unknown"
        declared = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "not declared"
        sections.extend(["=" * 78, f"{name}=={distribution.version} — {declared}", "-" * 78])
        notices: list[Path] = []
        for packaged in distribution.files or ():
            candidate = distribution.locate_file(packaged)
            if NOTICE_NAME.match(candidate.name) and candidate.is_file():
                notices.append(candidate)
        unique_notices = sorted(set(notices), key=lambda item: str(item).casefold())
        if unique_notices:
            for notice in unique_notices:
                sections.extend([f"[{notice.name}]", notice.read_text(encoding="utf-8", errors="replace").strip(), ""])
        else:
            fallback = AUDITED_FALLBACKS.get((name.casefold(), distribution.version))
            if not fallback or any(not item.is_file() for item in fallback):
                raise RuntimeError(f"python_license_file_missing:{name}=={distribution.version}")
            for notice in fallback:
                sections.extend(
                    [
                        f"[audited fallback: {notice.name}]",
                        notice.read_text(encoding="utf-8", errors="strict").strip(),
                        "",
                    ]
                )
    output.write_text("\n".join(sections) + "\n", encoding="utf-8", newline="\n")
    print(f"python_licenses={len(distributions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

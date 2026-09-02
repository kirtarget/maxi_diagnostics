"""Validate public school configuration and every referenced asset."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pydantic import ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from diagnostic.catalog import (  # noqa: E402
    Diagnostic, DiagnosticCatalog, _catalog_paths, load_catalog,
)
from diagnostic.jsonutil import load_json_file  # noqa: E402
from diagnostic.school import (  # noqa: E402
    BrandConfig, LinksConfig, SchoolConfig, load_school, validate_asset_file,
    validate_school_layout,
)


_SUPPORTED_ASSET_SUFFIXES = frozenset({".svg", ".png", ".jpg", ".jpeg"})
_MAX_ASSET_BYTES = 5 * 1024 * 1024
_MAX_CATALOG_BYTES = 1024 * 1024
_BROAD_QUESTION_TOPICS = frozenset(
    {
        "Английский язык",
        "Биология",
        "Информатика",
        "История",
        "Литература",
        "Математика",
        "Обществознание",
        "Русский язык",
        "Физика",
        "Химия",
    }
)


def _load_json(path: Path):
    return load_json_file(path, max_bytes=_MAX_CATALOG_BYTES)


def _safe_root(root: Path) -> tuple[Path | None, list[str]]:
    if not root.exists():
        return None, ["ERROR root_not_found"]
    if root.is_symlink():
        return None, ["ERROR root_symlink_not_allowed"]
    try:
        resolved = root.resolve(strict=True)
    except OSError:
        return None, ["ERROR root_not_found"]
    if not resolved.is_dir():
        return None, ["ERROR root_not_directory"]
    return resolved, []


def _asset_error(school_root: Path, relative_path: str) -> str | None:
    candidate = school_root / relative_path
    if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        return f"ERROR asset_outside_school: {relative_path}"
    current = school_root
    for part in Path(relative_path).parts:
        current = current / part
        if current.is_symlink():
            return f"ERROR asset_symlink_not_allowed: {relative_path}"
    try:
        resolved = candidate.resolve()
    except OSError:
        return f"ERROR asset_not_found: {relative_path}"
    if not resolved.is_relative_to(school_root):
        return f"ERROR asset_outside_school: {relative_path}"
    if not candidate.exists():
        return f"ERROR asset_not_found: {relative_path}"
    if not candidate.is_file():
        return f"ERROR asset_not_file: {relative_path}"
    if candidate.suffix.lower() not in _SUPPORTED_ASSET_SUFFIXES:
        return f"ERROR asset_unsupported_type: {relative_path}"
    try:
        if candidate.stat().st_size > _MAX_ASSET_BYTES:
            return f"ERROR asset_too_large: {relative_path}"
        validate_asset_file(school_root, relative_path)
    except OSError:
        return f"ERROR asset_unreadable: {relative_path}"
    except ValueError as exc:
        reason = str(exc)
        known = {
            "asset_too_large", "asset_unsafe_svg", "asset_invalid", "asset_unreadable",
            "asset_symlink_not_allowed", "asset_not_file",
        }
        return f"ERROR {reason if reason in known else 'asset_invalid'}: {relative_path}"
    return None


def _validation_error(label: str, path: str, exc: ValidationError) -> str:
    error = sorted(exc.errors(include_url=False), key=lambda item: tuple(map(str, item["loc"])))[0]
    location = ".".join(map(str, error["loc"])) or "root"
    error_type = str(error["type"])
    message = str(error.get("msg", ""))
    known_reasons = (
        "invalid_selection_limit", "invalid_option_reference", "invalid_input_variant",
        "invalid_quick_count", "duplicate_question_id", "duplicate_diagnostic_id",
        "invalid_asset_path", "invalid_public_url", "duplicate_offer_id",
    )
    reason = next((item for item in known_reasons if item in message), error_type)
    return f"ERROR {label}_invalid: {path} field={location} reason={reason}"


def validate_repository(root: Path) -> tuple[list[str], dict[str, int | str]]:
    root, errors = _safe_root(root)
    if root is None:
        return errors, {}
    school_root = root / "school"
    if not school_root.exists():
        return ["ERROR school_directory_not_found"], {}
    if school_root.is_symlink() or not school_root.is_dir():
        return ["ERROR unsafe_school_directory"], {}
    try:
        validate_school_layout(school_root)
    except (OSError, ValueError) as exc:
        errors.append(
            "ERROR school_unexpected_entry"
            if str(exc) == "school_unexpected_entry"
            else "ERROR school_layout_invalid"
        )

    brand = None
    links = None
    declared_assets: set[str] = set()
    for filename, model, label in (
        ("brand.json", BrandConfig, "brand"),
        ("links.json", LinksConfig, "links"),
    ):
        path = school_root / filename
        if path.is_symlink():
            errors.append(f"ERROR {label}_symlink_not_allowed: {filename}")
            continue
        try:
            raw_value = _load_json(path)
            if label == "brand" and isinstance(raw_value, dict) and isinstance(raw_value.get("logo"), str):
                declared_assets.add(raw_value["logo"])
            value = model.model_validate(raw_value)
        except ValidationError as exc:
            errors.append(_validation_error(label, filename, exc))
            continue
        except (OSError, UnicodeError, ValueError):
            errors.append(f"ERROR {label}_invalid: {filename}")
            continue
        if label == "brand":
            brand = value
        else:
            links = value

    diagnostics: list[Diagnostic] = []
    diagnostics_root = school_root / "diagnostics"
    if not diagnostics_root.exists() or not diagnostics_root.is_dir() or diagnostics_root.is_symlink():
        errors.append("ERROR diagnostics_directory_invalid")
    else:
        try:
            diagnostic_paths = _catalog_paths(diagnostics_root)
        except (OSError, ValueError) as exc:
            reason = str(exc)
            if reason.startswith("catalog_file_too_large:"):
                filename = reason.split(":", 1)[1]
                errors.append(f"ERROR catalog_too_large: diagnostics/{filename}")
                diagnostic_paths = ()
                reason = ""
            known = {
                "catalog_unexpected_entry", "catalog_filename_collision",
                "catalog_symlink_not_allowed", "too_many_diagnostics",
                "catalog_file_too_large", "catalog_total_too_large",
            }
            if reason:
                errors.append(f"ERROR {reason if reason in known else 'diagnostics_directory_invalid'}")
            diagnostic_paths = ()
        for path in diagnostic_paths:
            relative = f"diagnostics/{path.name}"
            if path.is_symlink():
                errors.append(f"ERROR catalog_symlink_not_allowed: {relative}")
                continue
            try:
                if path.stat().st_size > _MAX_CATALOG_BYTES:
                    errors.append(f"ERROR catalog_too_large: {relative}")
                    continue
            except OSError:
                errors.append(f"ERROR catalog_unreadable: {relative}")
                continue
            try:
                raw_diagnostic = _load_json(path)
                if isinstance(raw_diagnostic, dict):
                    for question in raw_diagnostic.get("questions", []):
                        if isinstance(question, dict) and isinstance(question.get("asset"), str):
                            declared_assets.add(question["asset"])
                diagnostics.append(Diagnostic.model_validate(raw_diagnostic))
                diagnostic = diagnostics[-1]
                for question in diagnostic.questions:
                    if question.topic in _BROAD_QUESTION_TOPICS:
                        errors.append(
                            "ERROR topic_too_broad: "
                            f"{relative} question={question.id}"
                        )
            except ValidationError as exc:
                errors.append(_validation_error("catalog", relative, exc))
            except (OSError, UnicodeError, ValueError):
                errors.append(f"ERROR catalog_invalid: {relative}")
        if not diagnostics:
            errors.append("ERROR diagnostics_not_found")

    if diagnostics:
        try:
            DiagnosticCatalog(diagnostics=tuple(diagnostics))
        except ValueError as exc:
            detail = str(exc)
            known_reasons = (
                "duplicate_diagnostic_id",
                "catalog_public_payload_too_large",
            )
            reason = next((item for item in known_reasons if item in detail), "catalog_invalid")
            errors.append(f"ERROR catalog_invalid: {reason}")
    assets: set[str] = set()
    if brand is not None:
        assets.add(brand.logo)
    for diagnostic in diagnostics:
        assets.update(
            asset
            for question in diagnostic.questions
            for asset in question.asset_paths
        )
    for relative_path in sorted(assets):
        error = _asset_error(school_root, relative_path)
        if error:
            errors.append(error)
    assets_root = school_root / "assets"
    if assets_root.exists() and assets_root.is_dir() and not assets_root.is_symlink():
        for candidate in sorted(assets_root.rglob("*"), key=lambda item: item.as_posix()):
            relative = candidate.relative_to(school_root).as_posix()
            if candidate.is_symlink():
                errors.append(f"ERROR asset_symlink_not_allowed: {relative}")
            elif candidate.is_file() and relative not in (assets | declared_assets):
                errors.append(f"ERROR asset_unreferenced: {relative}")

    if brand is not None and links is not None:
        try:
            SchoolConfig(root=school_root, brand=brand, links=links)
        except ValueError:
            errors.append("ERROR school_config_invalid")
    stats: dict[str, int | str] = {
        "school": brand.school_id if brand is not None else "unknown",
        "diagnostics": len(diagnostics),
        "questions": sum(len(diagnostic.questions) for diagnostic in diagnostics),
        "assets": len(assets),
    }
    if not errors:
        try:
            load_catalog(load_school(school_root))
        except (OSError, UnicodeError, ValueError) as exc:
            reason = str(exc)
            if not re.fullmatch(r"[a-z_]+(?::[A-Za-z0-9_.-]+)?", reason):
                reason = "runtime_invalid"
            errors.append(f"ERROR runtime_invalid: {reason}")
    return sorted(set(errors)), stats


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate school configuration")
    parser.add_argument("--root", help=argparse.SUPPRESS)
    try:
        arguments = parser.parse_args(argv)
        selected_root = root or (Path(arguments.root) if arguments.root else REPOSITORY_ROOT)
        errors, stats = validate_repository(selected_root)
    except (OSError, UnicodeError, ValueError):
        print("ERROR validation_failed")
        return 1
    if errors:
        for error in errors:
            print(error)
        return 1
    print(
        f"OK school={stats['school']} diagnostics={stats['diagnostics']} "
        f"questions={stats['questions']} assets={stats['assets']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

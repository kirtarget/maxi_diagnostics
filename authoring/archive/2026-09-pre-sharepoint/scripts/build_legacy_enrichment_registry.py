from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "school" / "diagnostics"
DEFAULT_MANIFEST = ROOT / "authoring" / "legacy-enrichment" / "manifest.json"

PARTITIONS = {
    "a": {
        "oge-mathematics-198.json",
        "oge-physics-197.json",
        "oge-chemistry-192.json",
    },
    "b": {
        "oge-biology-699.json",
        "ege-biology-1207.json",
        "ege-physics-1206.json",
        "oge-history-196.json",
        "ege-history-1211.json",
        "ege-informatics-1205.json",
    },
    "c": {
        "oge-social-studies-195.json",
        "ege-social-studies-1210.json",
        "oge-russian-language-379.json",
        "ege-russian-language-1213.json",
        "ege-english-language-1204.json",
        "oge-english-language-202.json",
        "ege-literature-1209.json",
        "ege-chemistry-1208.json",
    },
}


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_records() -> list[dict[str, Any]]:
    owner_by_file = {
        filename: partition
        for partition, filenames in PARTITIONS.items()
        for filename in filenames
    }
    records: list[dict[str, Any]] = []
    for path in sorted(DIAGNOSTICS.glob("*.json")):
        diagnostic = load_json(path)
        for question in diagnostic["questions"]:
            if question.get("explanation"):
                continue
            records.append(
                {
                    "partition": owner_by_file[path.name],
                    "file": path.name,
                    "diagnostic_id": diagnostic["id"],
                    "question_id": question["id"],
                    "type": question["type"],
                    "topic": question.get("topic", ""),
                    "title": question.get("title", ""),
                    "prompt_sha256": digest(question["prompt"]),
                    "correct_sha256": digest(question["correct"]),
                }
            )
    return records


def generate(path: Path) -> None:
    records = build_records()
    counts = {
        partition: sum(record["partition"] == partition for record in records)
        for partition in PARTITIONS
    }
    payload = {
        "schema_version": 1,
        "baseline_missing_explanations": len(records),
        "partition_counts": counts,
        "approved_answer_changes": [],
        "approved_prompt_changes": [],
        "records": records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"OK: recorded {len(records)} legacy questions; partitions={counts}")


def check(path: Path) -> None:
    manifest = load_json(path)
    errors: list[str] = []
    changed_answers: list[str] = []
    changed_prompts: list[str] = []
    missing_explanations: list[str] = []
    for record in manifest["records"]:
        diagnostic = load_json(DIAGNOSTICS / record["file"])
        question = next(
            (item for item in diagnostic["questions"] if item["id"] == record["question_id"]),
            None,
        )
        label = f'{record["diagnostic_id"]}/{record["question_id"]}'
        if question is None:
            errors.append(f"missing question: {label}")
            continue
        if digest(question["prompt"]) != record["prompt_sha256"]:
            changed_prompts.append(label)
        if digest(question["correct"]) != record["correct_sha256"]:
            changed_answers.append(label)
        explanation = question.get("explanation", "")
        if not isinstance(explanation, str) or not explanation.strip():
            missing_explanations.append(label)
        if "—" in explanation:
            errors.append(f"long dash in explanation: {label}")
    if missing_explanations:
        errors.append(f"missing explanations: {len(missing_explanations)}")
    approved_changes = sorted(manifest.get("approved_answer_changes", []))
    if sorted(changed_answers) != approved_changes:
        errors.append(
            "answer change registry mismatch: "
            f"actual={sorted(changed_answers)}, approved={approved_changes}"
        )
    approved_prompt_changes = sorted(manifest.get("approved_prompt_changes", []))
    if sorted(changed_prompts) != approved_prompt_changes:
        errors.append(
            "prompt change registry mismatch: "
            f"actual={sorted(changed_prompts)}, approved={approved_prompt_changes}"
        )
    if errors:
        raise SystemExit("ERROR:\n" + "\n".join(errors))
    print(
        "OK: all legacy explanations present; "
        f"answer changes={len(changed_answers)}; "
        f"prompt changes={len(changed_prompts)}"
    )
    for label in changed_answers:
        print(f"ANSWER_CHANGED: {label}")
    for label in changed_prompts:
        print(f"PROMPT_CHANGED: {label}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("generate", "check"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    if args.mode == "generate":
        generate(args.manifest)
    else:
        check(args.manifest)


if __name__ == "__main__":
    main()

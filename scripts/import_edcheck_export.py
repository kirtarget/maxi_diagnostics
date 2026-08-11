"""Convert a large Edcheck export into the bounded school diagnostic catalog."""

from __future__ import annotations

import argparse
import base64
import binascii
from collections.abc import Callable, Mapping
from collections import Counter, defaultdict
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


MAX_DIAGNOSTICS = 20
MAX_TOTAL_QUESTIONS = 200
DEFAULT_QUESTIONS_PER_DIAGNOSTIC = 20
MAX_SOURCE_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_SOURCE_IMAGE_HOSTS = frozenset(
    {"storage.yandexcloud.net", "latex.codecogs.com"}
)
NUMERIC_ANSWER = re.compile(
    r"[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]{1,3})?\Z"
)
EXAM_CODES = {"ЕГЭ": "ege", "ОГЭ": "oge"}
SUBJECT_NAMES = {
    "russian-language": "Русский язык",
    "mathematics": "Математика",
    "history": "История",
    "social-studies": "Обществознание",
    "physics": "Физика",
    "informatics": "Информатика",
    "chemistry": "Химия",
    "biology": "Биология",
    "literature": "Литература",
    "english-language": "Английский язык",
}
PDF_SAFE_REPLACEMENTS = str.maketrans(
    {
        "⋅": "·",
        "℃": "°C",
        "⠀": " ",
        "̆": "",
        "𝑡": "t",
    }
)


class ImportError(RuntimeError):
    """A controlled export or destination error."""


def _load_json(path: Path) -> Any:
    payload = path.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ImportError(f"UTF-8 BOM is not allowed: {path}")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportError(f"Invalid UTF-8 JSON: {path}") from exc


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFC", html.unescape(value)).translate(
        PDF_SAFE_REPLACEMENTS
    )
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith("C")
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _clean_prompt_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = (
        unicodedata.normalize("NFC", html.unescape(value))
        .translate(PDF_SAFE_REPLACEMENTS)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    normalized = "".join(
        character
        for character in normalized
        if character == "\n" or not unicodedata.category(character).startswith("C")
    )
    lines = (
        re.sub(r"[^\S\n]+", " ", line).strip()
        for line in normalized.split("\n")
    )
    return "\n".join(line for line in lines if line)


def _mathml_text(value: str) -> str:
    try:
        root = ET.fromstring(html.unescape(value))
    except ET.ParseError:
        return ""

    def render(element: ET.Element) -> str:
        tag = element.tag.rsplit("}", 1)[-1]
        children = list(element)
        if tag == "msup" and len(children) >= 2:
            return f"{render(children[0])}^({render(children[1])})"
        if tag == "msub" and len(children) >= 2:
            return f"{render(children[0])}_({render(children[1])})"
        if tag == "mfrac" and len(children) >= 2:
            return f"({render(children[0])})/({render(children[1])})"
        if tag == "msqrt":
            return f"√({''.join(render(child) for child in children)})"
        if tag == "mroot" and len(children) >= 2:
            return f"root({render(children[0])}, {render(children[1])})"
        content = "" if not element.text or element.text.isspace() else element.text
        for child in children:
            content += render(child)
            if child.tail and not child.tail.isspace():
                content += child.tail
        return content

    return re.sub(r"\s+", " ", render(root)).strip()


class _MathAwareHTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed_depth = 0
        self.found_math = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self.suppressed_depth:
            self.suppressed_depth += 1
            return
        attributes = dict(attrs)
        mathml = attributes.get("data-mathml")
        if mathml:
            formula = _mathml_text(mathml)
            if formula:
                self.parts.extend(("\n", formula, "\n"))
                self.suppressed_depth = 1
                self.found_math = True
                return
        if tag in {"br", "div", "li", "p", "tr"}:
            self.parts.append("\n")
        if tag == "img":
            label = attributes.get("title") or attributes.get("alt")
            if label:
                self.parts.extend((" ", label, " "))

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.suppressed_depth:
            self.suppressed_depth -= 1
            return
        if tag in {"div", "li", "p", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.suppressed_depth:
            self.parts.append(data)


class _InlineImageSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "img":
            return
        source = dict(attrs).get("src")
        if source and source.strip():
            self.sources.append(source.strip())

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)


def _inline_image_sources(question: dict[str, Any]) -> tuple[str, ...]:
    source = question.get("description_html")
    if not isinstance(source, str) or "img" not in source.casefold():
        return ()
    parser = _InlineImageSourceParser()
    parser.feed(source)
    return tuple(dict.fromkeys(parser.sources))


def _prompt_with_math(question: dict[str, Any]) -> str:
    source = question.get("description_html")
    if not isinstance(source, str) or "data-mathml" not in source:
        return ""
    parser = _MathAwareHTMLText()
    parser.feed(source)
    if not parser.found_math:
        return ""
    return _clean_prompt_text("".join(parser.parts))


def _topic(question: dict[str, Any], fallback: str) -> str:
    candidates = [question.get("theme")]
    candidates.extend(question.get("blocks") or [])
    candidates.append(fallback)
    for candidate in candidates:
        value = _clean_text(candidate)
        if value:
            return value[:128].rstrip()
    return fallback


def _prompt(question: dict[str, Any]) -> str | None:
    value = _prompt_with_math(question) or _clean_prompt_text(
        question.get("description_text")
    )
    if not 1 <= len(value) <= 4000:
        return None
    if question.get("images") or question.get("audio_file"):
        return None
    return value


def _explanation(question: Mapping[str, Any]) -> str | None:
    for key in ("solution", "answer_explanation", "explanation"):
        value = question.get(key)
        if not isinstance(value, str):
            continue
        cleaned = _clean_prompt_text(value)
        if cleaned and len(cleaned) <= 2000:
            return cleaned
    return None


def _normalized_answer(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    return _clean_text(str(value))


def _choice_question(
    question: dict[str, Any], prompt: str, topic: str
) -> dict[str, Any] | None:
    references = question.get("reference_answers")
    if not isinstance(references, list) or not 2 <= len(references) <= 50:
        return None

    labels: list[str] = []
    right_indices: list[int] = []
    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            return None
        label = _clean_text(reference.get("text"))
        if not 1 <= len(label) <= 500:
            return None
        labels.append(label)
        if reference.get("isRight") is True:
            right_indices.append(index)

    if not right_indices:
        correct_values = {
            _normalized_answer(value) for value in question.get("correct_answers") or []
        }
        right_indices = [index for index, label in enumerate(labels) if label in correct_values]

    source_type = question.get("type")
    if source_type == "one-variant" and len(right_indices) != 1:
        return None
    if source_type == "multiple-variants" and not right_indices:
        return None

    options = [
        {"id": f"o{index + 1}", "label": label}
        for index, label in enumerate(labels)
    ]
    correct = [f"o{index + 1}" for index in right_indices]
    converted: dict[str, Any] = {
        "id": f"q{question['question_id']}",
        "type": "single" if source_type == "one-variant" else "multiple",
        "topic": topic,
        "title": _question_title(question),
        "prompt": prompt,
        "options": options,
    }
    if source_type == "one-variant":
        converted["correct"] = correct[0]
    else:
        converted["selection_limit"] = len(correct)
        converted["correct"] = correct
    return converted


def _numeric_question(
    question: dict[str, Any], prompt: str, topic: str
) -> dict[str, Any] | None:
    answers = []
    for source_answer in question.get("correct_answers") or []:
        answer = _normalized_answer(source_answer)
        if not 1 <= len(answer) <= 64 or NUMERIC_ANSWER.fullmatch(answer) is None:
            return None
        if answer not in answers:
            answers.append(answer)
    if not 1 <= len(answers) <= 20:
        return None
    return {
        "id": f"q{question['question_id']}",
        "type": "input",
        "topic": topic,
        "title": _question_title(question),
        "prompt": prompt,
        "correct": answers,
    }


def _matching_sequence_question(
    question: dict[str, Any], prompt: str, topic: str
) -> dict[str, Any] | None:
    source_answers = question.get("correct_answers") or []
    answers = [_normalized_answer(value) for value in source_answers]
    if not answers or any(re.fullmatch(r"[0-9]", answer) is None for answer in answers):
        return None
    sequence = "".join(answers)
    if len(sequence) > 64:
        return None
    return {
        "id": f"q{question['question_id']}",
        "type": "input",
        "topic": topic,
        "title": _question_title(question),
        "prompt": f"{prompt}\nВведите последовательность цифр без пробелов.",
        "correct": [sequence],
    }


def _question_title(question: dict[str, Any]) -> str:
    number = question.get("number_in_exam") or question.get("question_index")
    return f"Задание {number}"


def _convert_question(question: dict[str, Any]) -> dict[str, Any] | None:
    prompt = _prompt(question)
    if prompt is None:
        return None
    subject = question.get("subject") or {}
    subject_name = SUBJECT_NAMES.get(subject.get("code"), _clean_text(subject.get("name")))
    topic = _topic(question, subject_name or "Общая подготовка")
    source_type = question.get("type")
    converted = None
    if source_type in {"one-variant", "multiple-variants"}:
        converted = _choice_question(question, prompt, topic)
    elif source_type == "short-answer":
        converted = _numeric_question(question, prompt, topic)
    elif source_type == "match":
        converted = _matching_sequence_question(question, prompt, topic)
    if converted is None:
        return None
    explanation = _explanation(question)
    if explanation is not None:
        converted["explanation"] = explanation
    image_sources = _inline_image_sources(question)
    if len(image_sources) > 5:
        return None
    if image_sources:
        converted["_asset_sources"] = list(image_sources)
    return converted


def _image_extension(payload: bytes) -> str:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, ValueError):
        root = None
    if root is not None and root.tag.rsplit("}", 1)[-1].casefold() == "svg":
        return ".svg"
    raise ImportError(
        f"Unsupported source image format: {payload[:12].hex()}"
    )


def _download_remote_image(source: str) -> bytes:
    parsed = urlsplit(source)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_SOURCE_IMAGE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.port not in {None, 443}
    ):
        raise ImportError("Unsafe source image URL")
    request = Request(source, headers={"User-Agent": "maxi-diagnostics-import/1"})
    last_error: OSError | ValueError | None = None
    for _attempt in range(3):
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - host allowlist above
                final = urlsplit(response.geturl())
                if (
                    final.scheme != "https"
                    or final.hostname not in ALLOWED_SOURCE_IMAGE_HOSTS
                    or final.port not in {None, 443}
                ):
                    raise ImportError("Unsafe source image redirect")
                payload = response.read(MAX_SOURCE_IMAGE_BYTES + 1)
            break
        except ImportError:
            raise
        except (OSError, ValueError) as exc:
            last_error = exc
    else:
        raise ImportError(
            f"Unable to download source image from {parsed.hostname}"
        ) from last_error
    if not payload or len(payload) > MAX_SOURCE_IMAGE_BYTES:
        raise ImportError("Source image is empty or too large")
    return payload


def _source_image_payload(
    source: str,
    fetch_remote: Callable[[str], bytes],
) -> tuple[bytes, str]:
    if source.startswith("data:"):
        header, separator, encoded = source.partition(",")
        if separator != "," or header.casefold() not in {
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/jpg;base64",
        }:
            raise ImportError("Unsupported inline source image")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImportError("Invalid inline source image") from exc
    else:
        parsed = urlsplit(source)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_SOURCE_IMAGE_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port not in {None, 443}
        ):
            raise ImportError("Unsafe source image URL")
        payload = fetch_remote(source)
    if not payload or len(payload) > MAX_SOURCE_IMAGE_BYTES:
        raise ImportError("Source image is empty or too large")
    return payload, _image_extension(payload)


def _materialize_diagnostics_assets(
    diagnostics: list[tuple[str, dict[str, Any]]],
    asset_directory: Path,
    *,
    fetch_remote: Callable[[str], bytes] = _download_remote_image,
) -> None:
    if not asset_directory.is_dir() or asset_directory.is_symlink():
        raise ImportError(f"Unsafe question asset destination: {asset_directory}")
    planned_files: list[tuple[Path, bytes]] = []
    planned_questions: list[tuple[dict[str, Any], list[str]]] = []
    payload_cache: dict[str, tuple[bytes, str]] = {}
    for _, diagnostic in diagnostics:
        for question in diagnostic["questions"]:
            sources = question.get("_asset_sources")
            if not sources:
                continue
            if not isinstance(sources, list) or not 1 <= len(sources) <= 5:
                raise ImportError("Invalid source image list")
            question_id = question.get("id")
            if not isinstance(question_id, str) or re.fullmatch(r"q[0-9]+", question_id) is None:
                raise ImportError("Unsafe source image question id")
            relative_paths: list[str] = []
            for index, source in enumerate(sources, 1):
                if not isinstance(source, str):
                    raise ImportError("Invalid source image URL")
                cached = payload_cache.get(source)
                if cached is None:
                    cached = _source_image_payload(source, fetch_remote)
                    payload_cache[source] = cached
                payload, extension = cached
                suffix = "" if len(sources) == 1 else f"-{index}"
                filename = f"{question_id}{suffix}{extension}"
                destination = asset_directory / filename
                if destination.is_symlink():
                    raise ImportError(f"Unsafe question asset destination: {destination}")
                planned_files.append((destination, payload))
                relative_paths.append(f"assets/questions/{filename}")
            planned_questions.append((question, relative_paths))

    for destination, payload in planned_files:
        destination.write_bytes(payload)
    for question, relative_paths in planned_questions:
        question.pop("_asset_sources", None)
        if len(relative_paths) == 1:
            question["asset"] = relative_paths[0]
        else:
            question["assets"] = relative_paths


def _select_diagnostics(
    questions: list[dict[str, Any]],
    tests: list[dict[str, Any]],
    per_diagnostic: int,
) -> tuple[list[tuple[str, dict[str, Any]]], Counter[str]]:
    questions_by_test: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        questions_by_test[question["test_id"]].append(question)

    tests_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for test in tests:
        exam = test.get("exam")
        subject = test.get("subject") or {}
        subject_code = subject.get("code")
        if exam in EXAM_CODES and subject_code in SUBJECT_NAMES:
            tests_by_group[(exam, subject_code)].append(test)

    diagnostics: list[tuple[str, dict[str, Any]]] = []
    skipped: Counter[str] = Counter()
    exam_order = {"ЕГЭ": 0, "ОГЭ": 1}
    groups = sorted(tests_by_group, key=lambda item: (exam_order[item[0]], item[1]))
    for exam, subject_code in groups:
        candidates: list[tuple[int, int, dict[str, Any], list[dict[str, Any]]]] = []
        for test in tests_by_group[(exam, subject_code)]:
            converted = []
            for question in sorted(
                questions_by_test.get(test["test_id"], []),
                key=lambda item: (item.get("question_index") or 0, item["question_id"]),
            ):
                result = _convert_question(question)
                if result is None:
                    skipped[str(question.get("type") or "unknown")] += 1
                else:
                    converted.append(result)
            candidates.append((len(converted), -int(test["test_id"]), test, converted))

        compatible_count, _, selected_test, converted = max(candidates, key=lambda item: item[:2])
        if compatible_count == 0:
            continue
        converted = converted[:per_diagnostic]
        test_id = int(selected_test["test_id"])
        diagnostic_id = f"{EXAM_CODES[exam]}-{subject_code}-{test_id}"
        filename = f"{diagnostic_id}.json"
        variant = selected_test.get("variant_number")
        mark = f"Вариант {variant}" if variant is not None else "Диагностика"
        diagnostic = {
            "id": diagnostic_id,
            "exam": exam,
            "subject": SUBJECT_NAMES[subject_code],
            "mark": mark,
            "quick_count": min(3, len(converted)),
            "scoring": {"max_score": 100, "score_unit": "accuracy_percent"},
            "questions": converted,
        }
        diagnostics.append((filename, diagnostic))

    if len(diagnostics) > MAX_DIAGNOSTICS:
        raise ImportError(f"Too many diagnostics: {len(diagnostics)}")
    total_questions = sum(len(diagnostic["questions"]) for _, diagnostic in diagnostics)
    if total_questions > MAX_TOTAL_QUESTIONS:
        raise ImportError(f"Too many questions: {total_questions}")
    return diagnostics, skipped


def _write_diagnostics(
    destination: Path, diagnostics: list[tuple[str, dict[str, Any]]]
) -> None:
    if not destination.is_dir() or destination.is_symlink():
        raise ImportError(f"Unsafe diagnostics destination: {destination}")
    for filename, diagnostic in diagnostics:
        path = destination / filename
        payload = json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n"
        path.write_text(payload, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to the Edcheck export directory")
    parser.add_argument(
        "--destination", type=Path, default=Path("school/diagnostics")
    )
    parser.add_argument(
        "--questions-per-diagnostic",
        type=int,
        default=DEFAULT_QUESTIONS_PER_DIAGNOSTIC,
    )
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.questions_per_diagnostic <= DEFAULT_QUESTIONS_PER_DIAGNOSTIC:
        parser.error("--questions-per-diagnostic must be between 1 and 20")

    source = arguments.source.resolve()
    questions = _load_json(source / "questions.json")
    tests = _load_json(source / "tests.json")
    if not isinstance(questions, list) or not isinstance(tests, list):
        raise ImportError("questions.json and tests.json must contain arrays")

    diagnostics, skipped = _select_diagnostics(
        questions, tests, arguments.questions_per_diagnostic
    )
    if not arguments.dry_run:
        destination = arguments.destination.resolve()
        asset_directory = destination.parent / "assets" / "questions"
        if not asset_directory.exists():
            assets_root = asset_directory.parent
            if not assets_root.is_dir() or assets_root.is_symlink():
                raise ImportError(f"Unsafe question asset destination: {asset_directory}")
            asset_directory.mkdir()
        _materialize_diagnostics_assets(diagnostics, asset_directory)
        _write_diagnostics(destination, diagnostics)

    total_questions = sum(len(item["questions"]) for _, item in diagnostics)
    print(
        json.dumps(
            {
                "diagnostics": len(diagnostics),
                "questions": total_questions,
                "files": [filename for filename, _ in diagnostics],
                "skipped_source_questions_by_type": dict(sorted(skipped.items())),
                "dry_run": arguments.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

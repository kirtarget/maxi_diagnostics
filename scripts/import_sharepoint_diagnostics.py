"""Append editor-approved SharePoint diagnostics to the school catalog.

The source documents are MAXIMUM editorial diagnostics exported as `.docx`. Every
file is a flat list of `Задание N` blocks with an optional option list, optional
tables, an optional `Решение:` and a mandatory `Ответ:` key. This converter maps
the machine-checkable subset onto catalog question types, extracts inline
figures, and records every skipped task with a reason in a Markdown report.

Every catalog question comes from these documents. A full re-run replaces exactly
the questions whose id starts with `sp-`, leaves every other byte of the file
alone, and must produce byte-identical output. The source directory therefore
has to hold the whole bank, the 20 base diagnostics included. A `--partial`
re-run replaces only the prefixes derived from its selected source files and
requires an explicit non-global `--report` path. Use it for a targeted export
when the whole bank is not available.

Subject, exam, season and topic come from the source filename. Thematic packages
are named too freely for that, so `--plan` supplies the same fields explicitly
for the files it lists and checks each of them against a SHA-256 content hash.
Their question ids carry the plan topic slug, which keeps two packages of one
subject and season apart.

    python scripts/import_sharepoint_diagnostics.py <docx-dir> [--plan plan.json]
    python scripts/import_sharepoint_diagnostics.py <docx-dir> --partial \
        --report authoring/sharepoint-import/targeted-report.md
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Literal, TypeAlias

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from diagnostic.numeric import is_valid_numeric_answer  # noqa: E402


ID_PREFIX = "sp-"
SOURCE_ARTIFACT = re.compile(r"q\d+(?:-\d+\.[^.]+)?\Z")
MAX_PROMPT_CHARS = 10000
MAX_EXPLANATION_CHARS = 2000
MAX_OPTION_LABEL_CHARS = 500
MAX_OPTIONS = 50
MAX_QUESTIONS_PER_DIAGNOSTIC = 200
MAX_CATALOG_FILE_BYTES = 1024 * 1024
MAX_QUESTION_ASSETS = 5
MAX_TEXT_VARIANTS = 20
MAX_ANSWER_VARIANTS = 20
MAX_TEXT_ANSWER_CHARS = 80
MAX_REFERENCED_ASSETS = 201
MAX_ASSET_SIDE = 900
DEFAULT_VERIFIED_AT = "1970-01-01"
SOURCE_URL = "https://maximumtest.ru/"
SOURCE_PROVIDER = "maximum_editorial"

SUBJECT_CODES = {
    "АЯ": "english-language",
    "БИО": "biology",
    "ИНФ": "informatics",
    "ИСТ": "history",
    "ЛИТ": "literature",
    "МА": "mathematics",
    "МАТ": "mathematics",
    "ОБЩ": "social-studies",
    "РЯ": "russian-language",
    "ФИЗ": "physics",
    "ХИМ": "chemistry",
}
SUBJECT_NAMES = {
    "english-language": "Английский язык",
    "biology": "Биология",
    "informatics": "Информатика",
    "history": "История",
    "literature": "Литература",
    "mathematics": "Математика",
    "social-studies": "Обществознание",
    "russian-language": "Русский язык",
    "physics": "Физика",
    "chemistry": "Химия",
}
TRUSTED_SOURCE_HASHES = {
    "chemistry-ege-2022": "af5c2a79a8d46c265f8a072c6abfd24be153cef7c20852aff1316821ba0a462a",
    "biology-ege-2022": "6f35b4d13e9896e62b3071a998e06881e3876a785c7f4b29da7d22c6c7f0fd4b",
    "mathematics-oge-2022": "105fef81980a74e066adc5ab430f7ae9cad4c7a6e7c1e343a313e2cc781b9c45",
    "russian-language-ege-2022": "d1b27c66126732e2c53e3bde730ecc955f359f825b8c34faafea87a8cabbad1f",
}
CHECKED_IN_SCORE_POLICY: dict[tuple[str, str, frozenset[int]], int] = {
    ("ЕГЭ", "chemistry", frozenset({1, 2, 3, 4, 5, 17})): 1,
    ("ЕГЭ", "biology", frozenset({18})): 2,
    ("ОГЭ", "mathematics", frozenset({6, 8, 9, 13})): 1,
    ("ЕГЭ", "russian-language", frozenset({4})): 1,
}
EXAM_CODES = {"ЕГЭ": "ege", "ОГЭ": "oge"}
EXAM_NAMES = {code: name for name, code in EXAM_CODES.items()}

FILENAME = re.compile(
    r"^(?P<subject>[А-ЯЁ]+)_(?P<exam>ЕГЭ|ОГЭ)_.*?_(?P<start>\d{2})-(?P<end>\d{2})"
    r"_.*Заданий\s*(?P<tasks>\d+)$"
)
TASK_HEADING = re.compile(r"^Задание\s*(\d+)\.?$")
SEASON = re.compile(r"^(?P<start>\d{2})-(?P<end>\d{2})$")
TOPIC_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OPEN_ANSWER = re.compile(r"максимальный балл", re.IGNORECASE)
# Editors label the two columns with either a bracket or a dot, and a table
# that uses dots is the same table.
# Latin capitals sneak into these tables as look-alikes of the Cyrillic
# enumeration letters, so a table can label its rows А, Б, B.
MATCHING_ITEM = re.compile(r"^([А-ЯЁA-Z])[.)]\s*(.*)$", re.DOTALL)
MATCHING_OPTION = re.compile(r"^(\d)[.)]\s*(.*)$", re.DOTALL)
INLINE_OPTION = re.compile(r"^(\d+)\)\s*\S")
INLINE_OPTION_NUMBER = re.compile(r"^\d+\)\s*")
FLATTENED_NUMBERED_CHOICE = re.compile(r"(?:^|\s)(?P<number>\d+)[.)]\s*(?P<label>.*?)(?=\s+\d+[.)]\s+|\Z)", re.DOTALL)
TABLE_NUMBERED_CHOICE = re.compile(r"^(?P<number>\d+)[.)]\s*(?P<label>.+)$", re.DOTALL)
MIN_INLINE_OPTIONS = 3
DIGITS = re.compile(r"\d+\Z")
NUMERIC_SHAPED = re.compile(r"[0-9,.+-]+\Z")
FIGURE_WORDS = re.compile(
    r"рисун|схем[аеуы]|график|чертёж|чертеж|изображени|фотограф|на рисунке|"
    r"диаграмм|таблиц[аеуы] на",
    re.IGNORECASE,
)
EXTERNAL_RESOURCE = re.compile(r"https?://|воспользуйтесь файлом|аудиозапис|прослушайте", re.IGNORECASE)
SEQUENCE_MARKERS = re.compile(r"^[А-ЯЁ]\)", re.MULTILINE)
SEQUENCE_HINT = "Введите последовательность цифр без пробелов."
# A two-column matching table the converter could not read stays in the prompt as
# `left | right` lines. That is unreadable, so the task is dropped instead.
FLATTENED_MATCHING = re.compile(r"^\s*(?:[А-ЯЁA-Z][.)]|_{3,})\s.*\|\s*\d[.)]\s", re.MULTILINE)
# The printed exam tells the student where to write the answer. The Mini App
# collects it, so those sentences only contradict what is on screen.
ANSWER_SHEET_SENTENCES = (
    re.compile(r"(?:\s*и)?\s*запиш\w+\s+в\s+таблиц\w+[^.]*(?:\.|$)", re.IGNORECASE),
    re.compile(r"\s*в\s+ответе?\s+запиш\w+[^.]*(?:\.|$)", re.IGNORECASE),
    re.compile(r"\s*запиш\w+\s+в\s+ответе\s+цифры[^.]*(?:\.|$)", re.IGNORECASE),
    re.compile(r"\s*запиш\w+\s+цифры,\s+под\s+которыми[^.]*(?:\.|$)", re.IGNORECASE),
)
UI_COLLECTS_THE_ANSWER = {"single", "multiple", "matching"}
WORD_FORMATION_HINT = re.compile(r"\|\s*(?P<hint>[A-Z]+(?:\s+[A-Z]+)*)\s*\Z")
AUXILIARY_WORDS = frozenset(
    {
        "am", "are", "is", "was", "were", "be", "been", "being", "do", "does",
        "did", "have", "has", "had", "can", "could", "will", "would", "shall",
        "should", "may", "might", "must", "not",
    }
)
PDF_SAFE_REPLACEMENTS = str.maketrans(
    {
        "⋅": "·",
        "∙": "·",
        "℃": "°C",
        "⠀": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        "̀": "",
        "́": "",
        "̆": "",
        "∠": "угол ",
        "ᵒ": "°",
        "‒": "-",
    }
)
# Liberation Sans has no Mathematical Alphanumeric Symbols; the compatibility
# decomposition of each is the plain Latin letter the author meant.
MATH_ALPHANUMERIC = range(0x1D400, 0x1D800)
BLANK_CELL = re.compile(r"^[_\s.·—–-]*$")


class ImportError(RuntimeError):  # noqa: A001 - a controlled failure, not the builtin
    """A controlled source or destination error."""


# --------------------------------------------------------------------------
# Source model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceCell:
    """A table cell with ordered paragraph text and embedded figures."""

    paragraphs: tuple[str, ...]
    images: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class SourceTable:
    """One docx table as a grid of per-cell paragraph lists."""

    rows: tuple[tuple[tuple[str, ...], ...], ...]
    cells: tuple[tuple[SourceCell, ...], ...] = ()

    @property
    def columns(self) -> int:
        return max((len(row) for row in self.rows), default=0)


@dataclass
class SourceTask:
    number: int
    prompt_blocks: list[str] = field(default_factory=list)
    prompt_tables: list[SourceTable] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    solution: list[str] = field(default_factory=list)
    answer: list[str] = field(default_factory=list)
    images: list[bytes] = field(default_factory=list)
    # The nodes retain the body order that the legacy split lists cannot carry.
    # `prompt_blocks` and `prompt_tables` remain populated for existing callers.
    prompt_nodes: list["PromptNode"] = field(default_factory=list)
    sequence_choices: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class PromptParagraph:
    text: str
    images: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class PromptTable:
    table: SourceTable


PromptNode: TypeAlias = PromptParagraph | PromptTable
ParagraphNode = PromptParagraph
TableNode = PromptTable


@dataclass(frozen=True)
class SingleAnswerSpec:
    indices: tuple[int, ...]

@dataclass(frozen=True)
class MultipleAnswerSpec:
    indices: tuple[int, ...]

@dataclass(frozen=True)
class MatchingAnswerSpec:
    items: tuple[str, ...]
    options: tuple[tuple[str, str], ...]
    key: str
    table: SourceTable | None = None

@dataclass(frozen=True)
class InputAnswerSpec:
    correct: tuple[str, ...]
    sequence: bool = False
    answer_format: str = "number"
    answer_length: int | None = None
    allow_reuse: bool | None = None
    markers: tuple[str, ...] = ()
    options: tuple[tuple[str, str], ...] = ()

@dataclass(frozen=True)
class TextAnswerSpec:
    correct: tuple[str, ...]


AnswerSpec: TypeAlias = (
    SingleAnswerSpec
    | MultipleAnswerSpec
    | MatchingAnswerSpec
    | InputAnswerSpec
    | TextAnswerSpec
)


@dataclass(frozen=True)
class PlanEntry:
    """One `--plan` record: the metadata a free-form filename cannot carry."""

    file_name: str
    content_hash: str
    subject_code: str
    exam: str
    year: int
    topic: str
    topic_slug: str
    declared_tasks: int


@dataclass(frozen=True)
class SourceFile:
    path: Path
    exam: str
    subject_code: str
    year: int
    declared_tasks: int
    tasks: tuple[SourceTask, ...]
    topic: str = ""
    topic_slug: str = ""
    content_hash: str = ""

    @property
    def slug(self) -> str:
        base = f"{self.subject_code}-{EXAM_CODES[self.exam]}-{self.year}"
        return f"{base}-{self.topic_slug}" if self.topic_slug else base


@dataclass
class Outcome:
    number: int
    status: Literal["imported", "skipped"]
    question_type: str = ""
    reason: str = ""
    images: int = 0


def _belongs_to_source_artifact(identifier: str, source_slug: str) -> bool:
    """Match one source's question or generated asset without catching topic slugs."""
    prefix = f"{ID_PREFIX}{source_slug}-"
    return identifier.startswith(prefix) and bool(
        SOURCE_ARTIFACT.fullmatch(identifier[len(prefix):])
    )


# --------------------------------------------------------------------------
# Text normalization
# --------------------------------------------------------------------------


def clean_line(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).translate(PDF_SAFE_REPLACEMENTS)
    normalized = "".join(
        unicodedata.normalize("NFKC", character)
        if ord(character) in MATH_ALPHANUMERIC
        else character
        for character in normalized
        if not unicodedata.category(character).startswith("C")
    )
    return re.sub(r"\s+", " ", normalized).strip()


def clean_block(parts: list[str]) -> str:
    lines = (clean_line(line) for part in parts for line in part.split("\n"))
    return "\n".join(line for line in lines if line)


def renders(value: str) -> bool:
    """Whether the bundled PDF fonts cover every character of the text."""
    from diagnostic.font_support import validate_report_text

    try:
        for line in value.split("\n"):
            validate_report_text(line)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# docx reading
# --------------------------------------------------------------------------


def _iter_blocks(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _paragraph_images(paragraph: Paragraph, relationships) -> list[bytes]:
    payloads = []
    for blip in paragraph._p.iter(qn("a:blip")):
        relationship_id = blip.get(qn("r:embed"))
        if not relationship_id or relationship_id not in relationships:
            continue
        payloads.append(relationships[relationship_id].target_part.blob)
    return payloads


def _paragraph_text(paragraph: Paragraph) -> str:
    parts: list[str] = []
    segment = ""
    alignment = None
    for element in paragraph._p.iter(qn("w:r")):
        run = Run(element, paragraph)
        if not run.text:
            continue
        current = "super" if run.font.superscript else "sub" if run.font.subscript else None
        if current != alignment:
            parts.append(f"^({segment})" if alignment == "super" else f"_({segment})" if alignment == "sub" else segment)
            segment = ""
            alignment = current
        segment += run.text
    parts.append(f"^({segment})" if alignment == "super" else f"_({segment})" if alignment == "sub" else segment)
    return "".join(parts)


def _read_table(table: Table, relationships=None) -> SourceTable:
    rows = []
    cell_rows = []
    for row in table.rows:
        cells = []
        source_cells = []
        for cell in row.cells:
            paragraphs = tuple(
                clean_line(_paragraph_text(paragraph))
                for paragraph in cell.paragraphs
                if clean_line(_paragraph_text(paragraph))
            )
            images = tuple(
                image
                for paragraph in cell.paragraphs
                for image in (
                    _paragraph_images(paragraph, relationships)
                    if relationships is not None
                    else []
                )
            )
            lines = paragraphs
            cells.append(lines)
            source_cells.append(SourceCell(paragraphs=paragraphs, images=images))
        rows.append(tuple(cells))
        cell_rows.append(tuple(source_cells))
    return SourceTable(rows=tuple(rows), cells=tuple(cell_rows))


def parse_document(path: Path) -> tuple[SourceTask, ...]:
    document = Document(str(path))
    relationships = document.part.rels
    tasks: list[SourceTask] = []
    current: SourceTask | None = None
    section = "prompt"
    for block in _iter_blocks(document):
        if isinstance(block, Table):
            if current is not None and section == "prompt":
                table = _read_table(block, relationships)
                current.prompt_tables.append(table)
                current.prompt_nodes.append(PromptTable(table))
            continue
        text = clean_line(_paragraph_text(block))
        heading = TASK_HEADING.match(text)
        if heading:
            current = SourceTask(number=int(heading.group(1)))
            tasks.append(current)
            section = "prompt"
            continue
        if current is None:
            continue
        marker = text.rstrip(":").strip().casefold()
        if marker == "варианты":
            section = "options"
            continue
        if marker == "решение":
            section = "solution"
            continue
        if marker == "ответ":
            section = "answer"
            continue
        images = _paragraph_images(block, relationships)
        if section == "prompt":
            current.images.extend(images)
            if text or images:
                current.prompt_nodes.append(PromptParagraph(text, tuple(images)))
        if not text:
            continue
        getattr(current, {"prompt": "prompt_blocks", "options": "options",
                          "solution": "solution", "answer": "answer"}[section]).append(text)
    for task in tasks:
        _fold_answer_explanation(task)
        _adopt_inline_options(task)
    return tuple(tasks)


def _adopt_inline_options(task: SourceTask) -> None:
    """Move an option list typed as plain `N)` prompt lines into `options`.

    Some editors skip the `Варианты:` marker, which leaves the choices inside the
    prompt and turns a pick-one task into an empty input box. Only a run anchored
    at one end of the prompt, numbered `1..N` without a gap, and answered by a
    single digit inside that range can be the option list: a numbered run the key
    reorders, or one the question text refers to, keeps its place.
    """
    if task.options or len(task.answer) != 1:
        return
    parts = [part.strip() for part in task.answer[0].strip().split("#")]
    if not all(len(part) == 1 and part.isdigit() for part in parts):
        return
    blocks = task.prompt_blocks
    head = 0
    while head < len(blocks) and INLINE_OPTION.match(blocks[head]):
        head += 1
    tail = len(blocks)
    while tail > 0 and INLINE_OPTION.match(blocks[tail - 1]):
        tail -= 1
    for start, stop in ((0, head), (tail, len(blocks))):
        run = blocks[start:stop]
        if len(run) < MIN_INLINE_OPTIONS or len(run) == len(blocks):
            continue
        numbers = [int(INLINE_OPTION.match(line).group(1)) for line in run]
        if numbers != list(range(1, len(run) + 1)):
            continue
        if any(not 1 <= int(part) <= len(run) for part in parts):
            continue
        # `Варианты:` blocks carry no numbering, so neither do these.
        task.options.extend(INLINE_OPTION_NUMBER.sub("", line) for line in run)
        del blocks[start:stop]
        removed = set(run)
        task.prompt_nodes[:] = [
            node
            for node in task.prompt_nodes
            if not isinstance(node, PromptParagraph) or node.text not in removed
        ]
        return


def _flattened_numbered_choices(task: SourceTask) -> list[tuple[str, str]]:
    """Read a numbered choice grid from one block without rewriting that block."""
    if task.sequence_choices:
        return list(task.sequence_choices)
    if task.number == 5:
        for table in task.prompt_tables:
            choices = _numbered_choice_table(table)
            if choices:
                return choices
    if task.options or len(task.prompt_blocks) != 1:
        return []
    text = task.prompt_blocks[0]
    found = list(FLATTENED_NUMBERED_CHOICE.finditer(text))
    if len(found) < 3 or found[0].group("number") != "1":
        return []
    numbers = [int(match.group("number")) for match in found]
    if numbers != list(range(1, len(numbers) + 1)):
        return []
    labels = [clean_line(match.group("label")) for match in found]
    if any(not label for label in labels):
        return []
    return list(zip((str(number) for number in numbers), labels))


def _numbered_choice_table(table: SourceTable) -> list[tuple[str, str]]:
    """Read the nine numbered cells of the known q05 three-by-three grid."""
    if len(table.rows) != 3 or table.columns != 3:
        return []
    choices: list[tuple[str, str]] = []
    for row in table.rows:
        for cell in row:
            if len(cell) != 1:
                return []
            found = TABLE_NUMBERED_CHOICE.fullmatch(cell[0])
            if found is None:
                return []
            choices.append((found.group("number"), clean_line(found.group("label"))))
    numbers = [int(number) for number, _ in choices]
    if numbers != list(range(1, 10)) or any(not label for _, label in choices):
        return []
    return choices


def _score_policy(exam: str, subject: str, position: int) -> int | None:
    """Return a primary score only for the checked-in evidence positions."""
    for (policy_exam, policy_subject, positions), score in CHECKED_IN_SCORE_POLICY.items():
        if exam == policy_exam and subject == policy_subject and position in positions:
            return score
    return None


def _repair_source_question(
    source: SourceFile, task: SourceTask, question: dict[str, Any]
) -> None:
    """Apply narrow, source-keyed repairs to known editorial transcription errors."""
    if TRUSTED_SOURCE_HASHES.get(source.slug) != source.content_hash:
        return
    slug = source.slug
    if slug == "chemistry-ege-2022" and task.number in {1, 2, 3}:
        for option in question.get("options", []):
            if option["label"] == "Со":
                option["label"] = "Co"
            elif option["label"] == "Не":
                option["label"] = "He"
        question["prompt"] = re.sub(r"(\d[.)]\s*)Со\b", r"\1Co", question["prompt"])
        question["prompt"] = re.sub(r"(\d[.)]\s*)Не\b", r"\1He", question["prompt"])
    elif slug == "chemistry-ege-2022" and task.number == 5:
        if question.get("explanation"):
            question["explanation"] = question["explanation"].replace("КОН", "KOH")
    elif slug == "chemistry-ege-2022" and task.number == 17:
        if question.get("explanation"):
            question["explanation"] = question["explanation"].replace("Сl", "Cl")
    elif slug == "biology-ege-2022" and task.number == 18:
        for key in ("items", "options"):
            for option in question.get(key, []):
                option["label"] = re.sub(
                    r"^A\)", "А)", option["label"]
                )
                option["label"] = re.sub(r"^B\)", "В)", option["label"])
                option["label"] = re.sub(r"^E\)", "Е)", option["label"])
    elif slug == "mathematics-oge-2022" and task.number in {6, 13}:
        question["prompt"] = re.sub(r"\s+([.,:;])", r"\1", question["prompt"])
        if question.get("explanation"):
            question["explanation"] = question["explanation"].rstrip()
            question["explanation"] = question["explanation"].rstrip(":")
    score = _score_policy(source.exam, source.subject_code, task.number)
    if score is not None:
        question["max_primary_score"] = score
        question["source"]["approval_status"] = "approved"
        question["source"]["exam_position"] = str(task.number)


def _fold_answer_explanation(task: SourceTask) -> None:
    """Some documents put the explanation into the answer block, after the key."""
    if len(task.answer) == 2 and task.answer[1].casefold().startswith("пояснени"):
        task.solution.append(task.answer.pop())


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(path: Path) -> dict[str, PlanEntry]:
    """Read the source plan, keyed by file name."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, PlanEntry] = {}
    for record in payload.get("sources", []):
        file_name = record["file_name"]
        if file_name in entries:
            raise ImportError(f"Duplicate plan entry: {file_name}")
        subject_code = record["subject"]
        if subject_code not in SUBJECT_NAMES:
            raise ImportError(f"Unknown subject in plan entry {file_name}")
        exam = EXAM_NAMES.get(record["exam"])
        if exam is None:
            raise ImportError(f"Unknown exam in plan entry {file_name}")
        season = SEASON.match(record["season"])
        if season is None:
            raise ImportError(f"Unknown season in plan entry {file_name}")
        topic_slug = record["topic_slug"]
        if not TOPIC_SLUG.match(topic_slug):
            raise ImportError(f"Unusable topic slug in plan entry {file_name}")
        topic = clean_line(record["topic"])
        if not topic:
            raise ImportError(f"Empty topic in plan entry {file_name}")
        entries[file_name] = PlanEntry(
            file_name=file_name,
            content_hash=record["content_hash"],
            subject_code=subject_code,
            exam=exam,
            year=2000 + int(season.group("end")),
            topic=topic,
            topic_slug=topic_slug,
            # The filename does not always name a count; the manifest block count
            # is then the only declaration the report can compare against.
            declared_tasks=int(
                record.get("declared_question_count") or record["task_blocks"]
            ),
        )
    if not entries:
        raise ImportError(f"No sources in plan {path}")
    return entries


def read_source_file(path: Path, entry: PlanEntry | None = None) -> SourceFile:
    if entry is not None:
        if file_digest(path) != entry.content_hash:
            raise ImportError(f"Source file does not match the plan hash: {path.name}")
        return SourceFile(
            path=path,
            exam=entry.exam,
            subject_code=entry.subject_code,
            year=entry.year,
            declared_tasks=entry.declared_tasks,
            tasks=parse_document(path),
            topic=entry.topic,
            topic_slug=entry.topic_slug,
            content_hash=file_digest(path),
        )
    match = FILENAME.match(path.stem)
    if match is None:
        raise ImportError(f"Unrecognized source filename: {path.name}")
    subject_code = SUBJECT_CODES.get(match.group("subject"))
    if subject_code is None:
        raise ImportError(f"Unknown subject code in {path.name}")
    return SourceFile(
        path=path,
        exam=match.group("exam"),
        subject_code=subject_code,
        year=2000 + int(match.group("end")),
        declared_tasks=int(match.group("tasks")),
        tasks=parse_document(path),
        content_hash=file_digest(path),
    )


# --------------------------------------------------------------------------
# Answer-key classification
# --------------------------------------------------------------------------


def _matching_table(
    tables: list[SourceTable],
) -> tuple[SourceTable, list[str], list[tuple[str, str]]] | None:
    """Return (source table, item labels, [(option digit, label)]) for a matching table."""
    for table in tables:
        if table.columns != 2 or len(table.rows) < 3:
            continue
        items: list[str] = []
        options: list[tuple[str, str]] = []
        for row in table.rows[1:]:
            if len(row) < 2:
                continue
            for line in row[0]:
                found = MATCHING_ITEM.match(line)
                if found:
                    items.append(line)
            for line in row[1]:
                found = MATCHING_OPTION.match(line)
                if found:
                    options.append((found.group(1), line))
        if len(items) >= 2 and len(options) >= 2:
            return table, items, options
    return None


def _render_table(table: SourceTable) -> str:
    """Flatten a layout table to one `cell | cell` line per row.

    Blank cells keep their column so a fill-in row still reads as a row.
    """
    choices = _numbered_choice_table(table)
    if choices:
        # A grid of numbered choices is a list the student picks from, not a
        # data table: one choice per line keeps the app from drawing a header.
        return "\n".join(f"{number}) {label}" for number, label in choices)
    lines = []
    for row in table.rows:
        cells = [
            " ".join(cell) if cell and not all(BLANK_CELL.match(line) for line in cell)
            else "___"
            for cell in row
        ]
        if any(cell != "___" for cell in cells) and not _is_answer_grid_row(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def build_prompt(task: SourceTask, *, skip_table: SourceTable | None = None) -> str:
    # A matching task shows its pairs as controls, so only that one table is
    # dropped. A data table the question reasons about has to stay.
    if task.prompt_nodes:
        parts: list[str] = []
        for node in task.prompt_nodes:
            if isinstance(node, PromptParagraph):
                if node.text:
                    parts.append(node.text)
            elif node.table is not skip_table:
                rendered = _render_table(node.table)
                if rendered:
                    parts.append(rendered)
        return clean_block(parts)
    parts = list(task.prompt_blocks)
    parts.extend(
        rendered
        for rendered in (
            _render_table(table)
            for table in task.prompt_tables
            if table is not skip_table
        )
        if rendered
    )
    return clean_block(parts)


def classify(task: SourceTask) -> tuple[str, AnswerSpec | str]:
    """Return (question_type, payload) or ("skip", reason)."""
    if any(OPEN_ANSWER.search(line) for line in (*task.answer, *task.solution)):
        return "skip", "open_answer"
    if len(task.answer) != 1 or not task.answer[0].strip():
        return "skip", "irregular_key"
    key = task.answer[0].strip()
    if key.endswith(".") and NUMERIC_SHAPED.fullmatch(key[:-1]):
        key = key[:-1]
    parts = [part.strip() for part in key.split("#")]
    if any(not part for part in parts):
        return "skip", "irregular_key"
    digit_parts = [part for part in parts if DIGITS.fullmatch(part)]

    # A `#`-joined set of multi-digit groups usually packs several sub-answers
    # into one task, which the runtime has no shape for. The one reading that is
    # not a guess is a set of reorderings of a single answer: the same digits in
    # the same count, written out because their order is free.
    if len(parts) > 1 and len(digit_parts) == len(parts) and any(len(p) > 1 for p in parts):
        reorderings = (
            not task.options
            and len(set(parts)) == len(parts)
            and len(parts) <= MAX_ANSWER_VARIANTS
            and len({tuple(sorted(part)) for part in parts}) == 1
            and all(is_valid_numeric_answer(part) for part in parts)
        )
        if not reorderings:
            return "skip", "irregular_key"
        return "input", InputAnswerSpec(tuple(parts), sequence=True)

    if task.options:
        if len(digit_parts) != len(parts) or any(len(part) != 1 for part in parts):
            return "skip", "irregular_key"
        indices = [int(part) for part in parts]
        if len(set(indices)) != len(indices):
            return "skip", "irregular_key"
        if any(not 1 <= index <= len(task.options) for index in indices):
            return "skip", "irregular_key"
        spec = SingleAnswerSpec if len(indices) == 1 else MultipleAnswerSpec
        return ("single" if len(indices) == 1 else "multiple"), spec(tuple(indices))

    matching = _matching_table(task.prompt_tables)
    if matching is not None and len(parts) == 1 and DIGITS.fullmatch(key):
        table, items, options = matching
        option_digits = {digit for digit, _ in options}
        if len(key) == len(items) and set(key) <= option_digits:
            return "matching", MatchingAnswerSpec(
                tuple(items), tuple(options), key, table
            )

    if len(parts) == 1 and is_valid_numeric_answer(key):
        variants = [key]
        if "," in key:
            variants.append(key.replace(",", "."))
        # A one-digit key is a single number, not a sequence to type unspaced.
        sequence = len(key) > 1 and bool(DIGITS.fullmatch(key))
        numbered = _flattened_numbered_choices(task)
        if (
            sequence
            and len(numbered) in {8, 9}
            and (len(numbered) == 9 or bool(task.sequence_choices))
            and len(key) == 3
            and set(key) <= {marker for marker, _ in numbered}
        ):
            return "input", InputAnswerSpec(
                tuple(variants),
                sequence=True,
                answer_format="sequence",
                answer_length=3,
                allow_reuse=True,
                markers=("А", "Б", "В"),
                options=tuple(numbered),
            )
        return "input", InputAnswerSpec(tuple(variants), sequence=sequence)

    # Numeric-looking but ungrammatical, e.g. a value with its error margin
    # concatenated (`0,100,01`).
    if any(NUMERIC_SHAPED.fullmatch(part) for part in parts):
        return "skip", "irregular_key"

    variants: list[str] = []
    for part in parts:
        cleaned = clean_line(part)
        if not 1 <= len(cleaned) <= MAX_TEXT_ANSWER_CHARS:
            return "skip", "irregular_key"
        if cleaned not in variants:
            variants.append(cleaned)
    if not 1 <= len(variants) <= MAX_TEXT_VARIANTS:
        return "skip", "irregular_key"
    return "text", TextAnswerSpec(tuple(variants))


# --------------------------------------------------------------------------
# Question construction
# --------------------------------------------------------------------------


def _glued_answer(prompt: str, variants: list[str]) -> bool:
    """Whether a word-formation key spells a phrase the student cannot type.

    These tasks end with the source word after a `|`. A few editorial keys write
    the expected phrase without its space (`wasimpressed`, `didnotbelieve`), so
    the only accepted spelling is one no reader would produce. The key is the
    editorial source and stays untouched; the task leaves the catalog instead.
    """
    last_line = prompt.rstrip().splitlines()[-1]
    match = WORD_FORMATION_HINT.search(last_line)
    if match is None or any(" " in variant for variant in variants):
        return False
    hint = match.group("hint").split()
    if len(hint) > 1:
        return True
    stem = hint[0].lower()
    for variant in variants:
        lowered = variant.lower()
        index = lowered.find(stem)
        if index > 0 and lowered[:index] in AUXILIARY_WORDS:
            return True
    return False


def _restore_sentence_end(match: re.Match[str]) -> str:
    """A clause cut out of the middle of a sentence takes the full stop with it.

    Hand it back unless the text before the cut already ends a sentence, so
    the author's «!..» and «?..» never gain an extra dot.
    """
    before = match.string[: match.start()].rstrip()
    if not match.group(0).rstrip().endswith(".") or not before or before[-1] in ".!?…":
        return ""
    return "."


ANSWER_GRID_CELL = re.compile(r"^(?:[A-ZА-ЯЁ]|[XYХУ]|\(?[А-ЯЁA-Z]\)?\s*_{2,})$")


def _is_answer_grid_row(cells: list[str]) -> bool:
    """A row of bare markers or blanks is the paper answer grid, not task data."""
    return all(cell == "___" or ANSWER_GRID_CELL.match(cell) for cell in cells)


def strip_answer_sheet_instructions(prompt: str) -> str:
    """Drop the sentences that tell the student where to write the answer."""
    lines = []
    for line in prompt.split("\n"):
        for pattern in ANSWER_SHEET_SENTENCES:
            line = pattern.sub(_restore_sentence_end, line)
        line = re.sub(r"\s+\.", ".", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and line != ".":
            lines.append(line)
    return "\n".join(lines)


def _option_label(value: str) -> str | None:
    # List punctuation reads as a typo once every option is its own control.
    cleaned = clean_line(value).rstrip(";,").rstrip()
    return cleaned if 1 <= len(cleaned) <= MAX_OPTION_LABEL_CHARS else None


def build_question(
    source: SourceFile,
    task: SourceTask,
    kind: str,
    payload: AnswerSpec,
    *,
    verified_at: str,
) -> dict[str, Any] | str:
    table = payload.table if isinstance(payload, MatchingAnswerSpec) else None
    prompt = build_prompt(task, skip_table=table if kind == "matching" else None)
    if kind in UI_COLLECTS_THE_ANSWER:
        prompt = strip_answer_sheet_instructions(prompt)
    if not prompt:
        return "empty_prompt"
    if (
        kind == "input"
        and isinstance(payload, InputAnswerSpec)
        and payload.sequence
        and not SEQUENCE_MARKERS.search(prompt)
    ):
        prompt = f"{prompt}\n{SEQUENCE_HINT}"
    if len(prompt) > MAX_PROMPT_CHARS:
        return "prompt_too_long"

    question: dict[str, Any] = {
        "id": f"{ID_PREFIX}{source.slug}-q{task.number}",
        "type": kind,
        "topic": source.topic or f"Задание {task.number}",
        "title": f"Задание {task.number}",
        "prompt": prompt,
        "max_primary_score": 1,
    }

    if kind == "single":
        if not isinstance(payload, SingleAnswerSpec):
            return "invalid_answer_spec"
        labels = [_option_label(option) for option in task.options]
        if any(label is None for label in labels) or not 1 <= len(labels) <= MAX_OPTIONS:
            return "invalid_options"
        question["options"] = [
            {"id": chr(ord("a") + index), "label": label}
            for index, label in enumerate(labels)
        ]
        correct = [chr(ord("a") + index - 1) for index in payload.indices]
        question["correct"] = correct[0]
    elif kind == "multiple":
        if not isinstance(payload, MultipleAnswerSpec):
            return "invalid_answer_spec"
        labels = [_option_label(option) for option in task.options]
        if any(label is None for label in labels) or not 1 <= len(labels) <= MAX_OPTIONS:
            return "invalid_options"
        question["options"] = [
            {"id": chr(ord("a") + index), "label": label}
            for index, label in enumerate(labels)
        ]
        correct = [chr(ord("a") + index - 1) for index in payload.indices]
        question["selection_limit"] = len(correct)
        question["correct"] = correct
    elif kind == "matching":
        if not isinstance(payload, MatchingAnswerSpec):
            return "invalid_answer_spec"
        items = [_option_label(item) for item in payload.items]
        options = [(digit, _option_label(label)) for digit, label in payload.options]
        if any(item is None for item in items) or any(label is None for _, label in options):
            return "invalid_options"
        if len(items) > MAX_OPTIONS or len(options) > MAX_OPTIONS:
            return "invalid_options"
        question["items"] = [
            {"id": f"i{index + 1}", "label": item} for index, item in enumerate(items)
        ]
        seen: dict[str, str] = {}
        option_entries = []
        for digit, label in options:
            if digit in seen:
                return "invalid_options"
            seen[digit] = f"o{digit}"
            option_entries.append({"id": f"o{digit}", "label": label})
        question["options"] = option_entries
        question["correct"] = {
            f"i{index + 1}": f"o{digit}" for index, digit in enumerate(payload.key)
        }
    elif kind == "text":
        if not isinstance(payload, TextAnswerSpec):
            return "invalid_answer_spec"
        if _glued_answer(prompt, payload.correct):
            return "glued_answer"
        question["correct"] = list(payload.correct)
        question["max_length"] = MAX_TEXT_ANSWER_CHARS
    else:
        if not isinstance(payload, InputAnswerSpec):
            return "invalid_answer_spec"
        question["correct"] = list(payload.correct)
        question["answer_format"] = payload.answer_format
        if payload.answer_format == "sequence":
            question["answer_format"] = "sequence"
            question["answer_length"] = payload.answer_length
            question["allow_reuse"] = payload.allow_reuse
            question["markers"] = list(payload.markers)

    explanation = clean_block(task.solution)
    if explanation and len(explanation) <= MAX_EXPLANATION_CHARS and renders(explanation):
        question["explanation"] = explanation

    question["source"] = {
        "provider": SOURCE_PROVIDER,
        "official_year": source.year,
        "approval_status": "draft",
        "source_kind": "original",
        "source_url": SOURCE_URL,
        "rights_status": "original",
        "verified_at": verified_at,
    }
    return question


# --------------------------------------------------------------------------
# Runtime validation
# --------------------------------------------------------------------------


def validate_question(question: dict[str, Any]) -> str | None:
    """Validate against the runtime models; `text` uses a probe of the shared base."""
    from pydantic import TypeAdapter, ValidationError

    from diagnostic.catalog import Question

    candidate = question
    if question["type"] == "text":
        candidate = {
            key: value for key, value in question.items()
            if key not in {"type", "correct", "max_length"}
        }
        candidate["type"] = "input"
        candidate["correct"] = ["1"]
        for variant in question["correct"]:
            if not 1 <= len(variant) <= MAX_TEXT_ANSWER_CHARS:
                return "invalid_text_variant"
        if not 1 <= len(question["correct"]) <= MAX_TEXT_VARIANTS:
            return "invalid_text_variant"
    try:
        TypeAdapter(Question).validate_python(candidate)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"][1:]) or "question"
        return f"invalid_{location}"
    return None


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------


def prepare_image(payload: bytes) -> tuple[bytes, str] | None:
    """Return (bytes, extension) downscaled to fit the school asset limits."""
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            fmt = (image.format or "").upper()
            width, height = image.size
            if fmt not in {"PNG", "JPEG"} or width <= 0 or height <= 0:
                return None
            if max(width, height) <= MAX_ASSET_SIDE:
                return payload, ".png" if fmt == "PNG" else ".jpg"
            scale = MAX_ASSET_SIDE / max(width, height)
            resized = image.convert("RGB" if fmt == "JPEG" else "RGBA").resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS,
            )
            buffer = io.BytesIO()
            resized.save(buffer, format=fmt, optimize=True)
            return buffer.getvalue(), ".png" if fmt == "PNG" else ".jpg"
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------


@dataclass
class Candidate:
    source: SourceFile
    task: SourceTask
    question: dict[str, Any]
    images: list[tuple[bytes, str]]
    outcome: Outcome


def load_answer_variants(path: Path) -> dict[str, list[str]]:
    """Read the editor's extra accepted wordings, keyed by question id.

    The converter rewrites every `sp-` question on each run, so a wording added
    by hand to the catalog would not survive. This file does.
    """
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants = payload.get("variants", {})
    if not isinstance(variants, dict):
        raise ImportError(f"`variants` must be an object in {path.name}")
    result: dict[str, list[str]] = {}
    for question_id, wordings in variants.items():
        if not isinstance(wordings, list) or not wordings:
            raise ImportError(f"Answer variants for {question_id} must be a non-empty list")
        cleaned = []
        for wording in wordings:
            if not isinstance(wording, str):
                raise ImportError(f"Answer variant for {question_id} is not a string")
            text = clean_line(wording)
            if not 1 <= len(text) <= MAX_TEXT_ANSWER_CHARS:
                raise ImportError(f"Answer variant for {question_id} is out of length range")
            cleaned.append(text)
        result[question_id] = cleaned
    return result


def apply_answer_variants(question: dict[str, Any], extra: list[str]) -> str | None:
    """Add the editor's wordings to a free-text key, or say why they cannot go in."""
    from diagnostic.text_answers import normalize_text_answer

    if question["type"] != "text":
        return "answer_variants_need_a_text_question"
    accepted = list(question["correct"])
    seen = {normalize_text_answer(value) for value in accepted}
    for wording in extra:
        normalized = normalize_text_answer(wording)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        accepted.append(wording)
    if len(accepted) > MAX_TEXT_VARIANTS:
        return "too_many_answer_variants"
    question["correct"] = accepted
    return None


def convert_file(
    source: SourceFile,
    verified_at: str,
    answer_variants: dict[str, list[str]] | None = None,
) -> tuple[list[Candidate], list[Outcome]]:
    candidates: list[Candidate] = []
    outcomes: list[Outcome] = []
    variants = answer_variants or {}
    for task in source.tasks:
        if _has_table_cell_figure(task):
            outcomes.append(
                Outcome(task.number, "skipped", reason="unsupported_table_cell_figure")
            )
            continue
        kind, payload = classify(task)
        if kind == "skip":
            outcomes.append(Outcome(task.number, "skipped", reason=str(payload)))
            continue
        question = build_question(source, task, kind, payload, verified_at=verified_at)
        if isinstance(question, str):
            outcomes.append(Outcome(task.number, "skipped", kind, question))
            continue
        _repair_source_question(source, task, question)
        extra = variants.get(question["id"])
        if extra:
            problem = apply_answer_variants(question, extra)
            if problem is not None:
                raise ImportError(f"{problem}: {question['id']}")

        prepared = [prepare_image(payload_bytes) for payload_bytes in task.images]
        reason = _rejection(question, prepared)
        if reason is not None:
            outcomes.append(Outcome(task.number, "skipped", kind, reason))
            continue
        images = [image for image in prepared if image is not None]
        candidates.append(
            Candidate(
                source, task, question, images,
                Outcome(task.number, "imported", kind, images=len(images)),
            )
        )
    return candidates, outcomes


def _rejection(
    question: dict[str, Any], images: list[tuple[bytes, str] | None]
) -> str | None:
    """Why this converted question cannot ship, or None when it can."""
    if any(image is None for image in images):
        return "unreadable_figure"
    if len(images) > MAX_QUESTION_ASSETS:
        return "too_many_figures"
    if not images and FIGURE_WORDS.search(question["prompt"]):
        return "missing_figure"
    if len(FLATTENED_MATCHING.findall(question["prompt"])) >= 2:
        return "unreadable_matching"
    if EXTERNAL_RESOURCE.search(question["prompt"]):
        return "external_resource"
    return validate_question(question)


def _has_table_cell_figure(task: SourceTask) -> bool:
    """Table-cell figures cannot retain their relative layout in the catalog."""
    return any(
        cell.images
        for table in task.prompt_tables
        for row in table.cells
        for cell in row
    )


def allocate_assets(
    candidates: list[Candidate], budget: int
) -> tuple[dict[str, str], list[tuple[Candidate, str]]]:
    """Grant figure budget round-robin across source files, largest cost last.

    Returns the digest-to-relative-path map and the candidates dropped because
    the catalog's 201-reference ceiling had no room left for their figures.
    """
    by_file: dict[Path, list[Candidate]] = {}
    for candidate in candidates:
        if candidate.images:
            by_file.setdefault(candidate.source.path, []).append(candidate)
    granted: dict[str, str] = {}
    dropped: list[tuple[Candidate, str]] = []
    queues = [list(items) for _, items in sorted(by_file.items())]
    while any(queues):
        for queue in queues:
            if not queue:
                continue
            candidate = queue.pop(0)
            digests = [
                hashlib.sha256(payload).hexdigest() for payload, _ in candidate.images
            ]
            new = {digest for digest in digests if digest not in granted}
            if len(granted) + len(new) > budget:
                dropped.append((candidate, "asset_budget"))
                continue
            paths = []
            for index, (digest, (_, extension)) in enumerate(zip(digests, candidate.images)):
                if digest not in granted:
                    granted[digest] = (
                        f"assets/questions/{candidate.question['id']}-{index + 1}{extension}"
                    )
                paths.append(granted[digest])
            unique_paths = list(dict.fromkeys(paths))
            if len(unique_paths) == 1:
                candidate.question["asset"] = unique_paths[0]
            else:
                candidate.question["assets"] = unique_paths
    return granted, dropped


# --------------------------------------------------------------------------
# Catalog writing
# --------------------------------------------------------------------------


@dataclass
class Target:
    """A catalog file split so untouched questions keep their exact bytes."""

    path: Path
    payload: dict[str, Any]
    head: str
    chunks: list[tuple[str, str]]
    tail: str


def read_target(path: Path) -> Target:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    opening = text.index("[", text.index('"questions"'))
    decoder = json.JSONDecoder()
    position = opening + 1
    chunks: list[tuple[str, str]] = []
    while text[position] in " \n\r\t,":
        position += 1
    while text[position] != "]":
        question, end = decoder.raw_decode(text, position)
        chunks.append((str(question.get("id", "")), text[position:end]))
        position = end
        while text[position] in " \n\r\t,":
            position += 1
    return Target(path, payload, text[: opening + 1], chunks, text[position:])


def render_target(target: Target, chunks: list[tuple[str, str]]) -> str:
    """Rewrite the questions array, leaving every other byte of the file alone.

    `full_count` belongs to the editor, so nothing here writes or moves it.
    """
    body = ",".join(f"\n    {chunk}" for _, chunk in chunks)
    return f"{target.head}{body}\n  {target.tail}"


def render_question(question: dict[str, Any]) -> str:
    """Serialize one appended question at the catalog's array-item indent."""
    encoded = json.dumps(question, ensure_ascii=False, indent=2)
    return encoded.replace("\n", "\n    ")


def _candidate_sort_key(candidate: Candidate) -> tuple[bool, int, str, int]:
    return (
        bool(candidate.source.topic_slug),
        candidate.source.year,
        candidate.source.path.name,
        candidate.task.number,
    )


def render_partial_chunks(
    target: Target,
    additions: list[Candidate],
    selected_slugs: set[str],
) -> list[tuple[str, str]]:
    """Replace selected source groups at their first existing position."""
    by_slug: dict[str, list[Candidate]] = {slug: [] for slug in selected_slugs}
    for candidate in additions:
        by_slug[candidate.source.slug].append(candidate)
    for group in by_slug.values():
        group.sort(key=_candidate_sort_key)

    anchored: dict[int, list[tuple[str, str]]] = {}
    appended: list[list[Candidate]] = []
    for slug, group in sorted(by_slug.items()):
        first = next(
            (
                index
                for index, (identifier, _) in enumerate(target.chunks)
                if _belongs_to_source_artifact(identifier, slug)
            ),
            None,
        )
        rendered = [
            (candidate.question["id"], render_question(candidate.question))
            for candidate in group
        ]
        if first is None:
            if group:
                appended.append(group)
        else:
            anchored[first] = rendered
    appended.sort(key=lambda group: _candidate_sort_key(group[0]))

    chunks: list[tuple[str, str]] = []
    for index, chunk in enumerate(target.chunks):
        chunks.extend(anchored.get(index, []))
        if any(
            _belongs_to_source_artifact(chunk[0], slug) for slug in selected_slugs
        ):
            continue
        chunks.append(chunk)
    for group in appended:
        chunks.extend(
            (candidate.question["id"], render_question(candidate.question))
            for candidate in group
        )
    return chunks


def load_targets(diagnostics_root: Path) -> dict[tuple[str, str], Target]:
    targets = {}
    for path in sorted(diagnostics_root.glob("*.json")):
        target = read_target(path)
        targets[(target.payload["exam"], target.payload["subject"])] = target
    return targets


def write_diagnostic(path: Path, encoded: str) -> None:
    if len(encoded.encode("utf-8")) > MAX_CATALOG_FILE_BYTES:
        raise ImportError(f"Catalog file exceeds 1 MiB: {path.name}")
    if path.read_text(encoding="utf-8") != encoded:
        path.write_text(encoded, encoding="utf-8", newline="\n")


def write_report(
    path: Path,
    per_file: list[tuple[SourceFile, Path, list[Outcome]]],
    verified_at: str,
    *,
    partial: bool = False,
) -> None:
    scope_note = (
        "Это отчёт частичного импорта. Он покрывает только выбранные исходники. "
        "Остальные задания и ресурсы каталога сохранены."
        if partial
        else "Каталог школы состоит только из этих заданий."
    )
    lines = [
        "# Импорт диагностик SharePoint",
        "",
        f"Сгенерировано `python scripts/import_sharepoint_diagnostics.py <docx-dir>` "
        f"({verified_at}).",
        "",
        f"{scope_note} Текст задания, варианты и ключ взяты из редакционно "
        "утверждённых документов MAXIMUM. Импортёр применяет только узкие "
        "нормализации и исправления, разрешённые для источника с совпавшим "
        "SHA-256: канонизацию Unicode и пробелов, исправление известных "
        "OCR-похожих символов и пунктуации, а также проверенное удаление "
        "дублирующего маркера. Тема "
        "берётся из плана источников, а без плана каждому вопросу проставлена "
        "тема «Задание N». Первичный балл берётся из закреплённой score policy "
        "только для проверенных позиций, остальные остаются со статусом draft. "
        "Раздел «Темы, требующие "
        "сопоставления» "
        "перечисляет их по предметам, чтобы методист заполнил таблицу «позиция КИМ → "
        "тема». Только позиции из score policy получают `approval_status = approved`; "
        "остальные требуют предметной редактуры.",
        "",
        "## Итоги",
        "",
        "| Файл | Экзамен | Предмет | Каталог | Заданий | Импортировано | Пропущено |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for source, target, outcomes in per_file:
        imported = sum(1 for outcome in outcomes if outcome.status == "imported")
        lines.append(
            f"| {source.path.name} | {source.exam} | "
            f"{SUBJECT_NAMES[source.subject_code]} | {target.name} | "
            f"{len(outcomes)} | {imported} | {len(outcomes) - imported} |"
        )

    lines.extend(
        [
            "",
            "## Пропущенные задания",
            "",
            "Каждое задание, которое конвертер не перенёс, и причина.",
            "",
            "| Файл | Задание | Тип | Причина |",
            "|---|---:|---|---|",
        ]
    )
    skipped = [
        (source, outcome)
        for source, _, outcomes in per_file
        for outcome in sorted(outcomes, key=lambda item: item.number)
        if outcome.status == "skipped"
    ]
    for source, outcome in skipped:
        lines.append(
            f"| {source.path.name} | {outcome.number} "
            f"| {outcome.question_type or '-'} | {outcome.reason} |"
        )
    if not skipped:
        lines.append("| - | - | - | - |")

    lines.extend(
        [
            "",
            "## Темы, требующие сопоставления",
            "",
            "У импортированных заданий без записи в плане тема равна «Задание N». "
            "Заполните позицию КИМ и тему для каждого номера в списке.",
            "",
            "| Каталог | Экзамен | Предмет | Документ | Задания |",
            "|---|---|---|---|---|",
        ]
    )
    for source, target, outcomes in sorted(per_file, key=lambda item: item[1].name):
        numbers = [
            str(outcome.number)
            for outcome in sorted(outcomes, key=lambda item: item.number)
            if outcome.status == "imported"
        ]
        if not numbers:
            continue
        lines.append(
            f"| {target.name} | {source.exam} | {SUBJECT_NAMES[source.subject_code]} "
            f"| {source.path.name} | {', '.join(numbers)} |"
        )

    lines.append("")
    for source, target, outcomes in per_file:
        note = (
            ""
            if len(outcomes) == source.declared_tasks
            else (
                " Расхождение означает, что в документе заголовок «Задание N» "
                "оформлен нестандартно и соседние задания слиплись в один блок; "
                "такой блок уходит в пропуски с причиной `irregular_key`."
            )
        )
        lines.extend(
            [
                f"## {source.path.name}",
                "",
                f"Каталог: `school/diagnostics/{target.name}`. "
                f"Заявлено заданий в имени файла: {source.declared_tasks}, "
                f"найдено блоков: {len(outcomes)}.{note}",
                "",
                "| Задание | Итог | Тип | Причина | Рисунков |",
                "|---:|---|---|---|---:|",
            ]
        )
        for outcome in sorted(outcomes, key=lambda item: item.number):
            lines.append(
                f"| {outcome.number} | {outcome.status} | {outcome.question_type or '-'} "
                f"| {outcome.reason or '-'} | {outcome.images} |"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Directory holding the source .docx files")
    parser.add_argument(
        "--plan",
        type=Path,
        help="JSON plan naming subject, exam, season and topic per source file",
    )
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--answer-variants",
        type=Path,
        help="JSON file of extra accepted wordings, keyed by question id",
    )
    parser.add_argument(
        "--verified-at",
        default=None,
        help=(
            "Explicit editorial verification date stamped on every imported question "
            f"(defaults to the non-editorial sentinel {DEFAULT_VERIFIED_AT})"
        ),
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help=(
            "Replace only questions and assets belonging to the selected source files. "
            "Requires an explicit non-global --report path."
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Markdown report path. Required for --partial; defaults to the global report.",
    )
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)

    root: Path = arguments.root.resolve()
    diagnostics_root = root / "school" / "diagnostics"
    assets_root = root / "school" / "assets" / "questions"
    default_report_path = root / "authoring" / "sharepoint-import" / "report.md"
    if arguments.partial and arguments.report is None:
        parser.error("--partial requires an explicit --report path")
    report_path = (
        (arguments.report if arguments.report.is_absolute() else root / arguments.report).resolve()
        if arguments.report
        else default_report_path
    )
    if arguments.partial and report_path == default_report_path.resolve():
        parser.error("--partial cannot overwrite the global sharepoint-import/report.md")
    verified_at = str(arguments.verified_at or DEFAULT_VERIFIED_AT)

    targets = load_targets(diagnostics_root)

    plan = load_plan(arguments.plan) if arguments.plan else {}
    answer_variants = load_answer_variants(
        arguments.answer_variants or root / "authoring" / "answer-variants.json"
    )
    sources = [
        read_source_file(path, plan.get(path.name))
        for path in sorted(arguments.source.resolve().glob("*.docx"))
    ]
    if not sources:
        raise ImportError(f"No .docx files under {arguments.source}")
    selected_slugs = {source.slug for source in sources}
    kept_assets = {
        path.relative_to(root / "school").as_posix()
        for path in sorted((root / "school" / "assets").rglob("*"))
        if path.is_file()
        and (
            (not arguments.partial and not path.name.startswith(ID_PREFIX))
            or (
                arguments.partial
                and not any(
                    _belongs_to_source_artifact(path.name, slug)
                    for slug in selected_slugs
                )
            )
        )
    }

    candidates: list[Candidate] = []
    outcomes_by_source: dict[Path, list[Outcome]] = {}
    target_by_source: dict[Path, Path] = {}
    for source in sources:
        key = (source.exam, SUBJECT_NAMES[source.subject_code])
        if key not in targets:
            raise ImportError(f"No catalog diagnostic for {key}")
        target = targets[key]
        target_by_source[source.path] = target.path
        file_candidates, file_outcomes = convert_file(source, verified_at, answer_variants)
        candidates.extend(file_candidates)
        outcomes_by_source[source.path] = file_outcomes

    granted, dropped = allocate_assets(candidates, MAX_REFERENCED_ASSETS - len(kept_assets))
    dropped_ids = {candidate.question["id"] for candidate, _ in dropped}
    for candidate, reason in dropped:
        outcomes_by_source[candidate.source.path].append(
            Outcome(candidate.task.number, "skipped", candidate.question["type"], reason)
        )
    candidates = [item for item in candidates if item.question["id"] not in dropped_ids]
    for candidate in candidates:
        outcomes_by_source[candidate.source.path].append(candidate.outcome)

    grouped: dict[Path, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(target_by_source[candidate.source.path], []).append(candidate)

    written: list[tuple[str, int, int]] = []
    for target in sorted(targets.values(), key=lambda item: item.path):
        additions = sorted(
            grouped.get(target.path, []),
            # Base diagnostics carry no topic slug and sort first, because the
            # leading questions are the full diagnostic and the rest is bank.
            key=_candidate_sort_key,
        )
        if arguments.partial:
            chunks = render_partial_chunks(target, additions, selected_slugs)
            kept_count = sum(
                1
                for identifier, _ in target.chunks
                if not any(
                    _belongs_to_source_artifact(identifier, slug)
                    for slug in selected_slugs
                )
            )
        else:
            kept = [
                chunk for chunk in target.chunks if not chunk[0].startswith(ID_PREFIX)
            ]
            chunks = kept + [
                (candidate.question["id"], render_question(candidate.question))
                for candidate in additions
            ]
            kept_count = len(kept)
        collisions = [
            identifier
            for identifier, count in Counter(identifier for identifier, _ in chunks).items()
            if count > 1
        ]
        if collisions:
            raise ImportError(
                f"Duplicate question ids in {target.path.name}: "
                f"{', '.join(sorted(collisions)[:10])}"
            )
        if len(chunks) > MAX_QUESTIONS_PER_DIAGNOSTIC:
            raise ImportError(f"Too many questions in {target.path.name}: {len(chunks)}")
        written.append((target.path.name, kept_count, len(additions)))
        if not arguments.dry_run:
            write_diagnostic(target.path, render_target(target, chunks))

    if not arguments.dry_run:
        assets_root.mkdir(parents=True, exist_ok=True)
        for existing in sorted(assets_root.glob(f"{ID_PREFIX}*")):
            if not arguments.partial or any(
                _belongs_to_source_artifact(existing.name, slug)
                for slug in selected_slugs
            ):
                existing.unlink()
        payload_by_digest = {
            hashlib.sha256(payload).hexdigest(): payload
            for candidate in candidates
            for payload, _ in candidate.images
        }
        for digest, relative in sorted(granted.items()):
            (root / "school" / relative).write_bytes(payload_by_digest[digest])
        write_report(
            report_path,
            [
                (source, target_by_source[source.path], outcomes_by_source[source.path])
                for source in sources
            ],
            verified_at,
            partial=arguments.partial,
        )

    reasons: dict[str, int] = {}
    for outcomes in outcomes_by_source.values():
        for outcome in outcomes:
            if outcome.status == "skipped":
                reasons[outcome.reason] = reasons.get(outcome.reason, 0) + 1
    print(
        json.dumps(
            {
                "sources": len(sources),
                "imported": len(candidates),
                "text_questions": sum(
                    1 for item in candidates if item.question["type"] == "text"
                ),
                "assets": len(granted),
                "skipped_by_reason": dict(sorted(reasons.items())),
                "diagnostics": [
                    {"file": name, "existing": kept, "appended": added}
                    for name, kept, added in written
                ],
                "dry_run": arguments.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

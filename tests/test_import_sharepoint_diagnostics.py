import io
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from docx import Document
from docx.shared import Inches
from PIL import Image

from scripts import import_sharepoint_diagnostics as importer


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "ХИМ_ОГЭ_Диагностика_21-22_Заданий 8.docx"


def _png(width: int = 40, height: int = 30) -> io.BytesIO:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _task(document, number: int) -> None:
    document.add_paragraph(f"Задание {number}")


def _answer(document, solution: str | None, key: str) -> None:
    if solution is not None:
        document.add_paragraph("Решение:")
        document.add_paragraph(solution)
    document.add_paragraph("Ответ:")
    document.add_paragraph(key)


def test_import_preserves_grouped_superscripts_and_subscripts(tmp_path):
    document = Document()
    _task(document, 1)
    prompt = document.add_paragraph("Решите уравнение: 4")
    prompt.add_run("x").font.superscript = True
    prompt.add_run(" – 3").font.superscript = True
    prompt.add_run(" = 1/8")
    document.add_paragraph("Решение:")
    solution = document.add_paragraph("2")
    solution.add_run("2(x – 3)").font.superscript = True
    solution.add_run(" = 2")
    solution.add_run("–3").font.superscript = True
    document.add_paragraph("Ответ:")
    document.add_paragraph("1,5")
    _task(document, 2)
    table = document.add_table(rows=1, cols=1)
    formula = table.cell(0, 0).paragraphs[0]
    formula.add_run("H")
    formula.add_run("2").font.subscript = True
    formula.add_run("O")
    _answer(document, None, "1")
    source = tmp_path / "formula.docx"
    document.save(source)

    tasks = importer.parse_document(source)
    assert tasks[0].prompt_blocks == ["Решите уравнение: 4^(x – 3) = 1/8"]
    assert tasks[0].solution == ["2^(2(x – 3)) = 2^(–3)"]
    assert tasks[0].answer == ["1,5"]
    assert tasks[1].prompt_tables[0].rows == ((("H_(2)O",),),)


def build_source_document(path: Path) -> None:
    """One task per supported mapping, plus an irregular key and a figure."""
    document = Document()

    _task(document, 1)
    document.add_paragraph("Выберите одно вещество.")
    document.add_paragraph("Варианты:")
    for label in ("Кислород", "Азот", "Хлор"):
        document.add_paragraph(label)
    _answer(document, "Хлор стоит третьим в списке.", "3")

    _task(document, 2)
    document.add_paragraph("Выберите два вещества.")
    document.add_paragraph("Варианты:")
    for label in ("Медь", "Сера", "Железо", "Неон"):
        document.add_paragraph(label)
    _answer(document, None, "1#3")

    _task(document, 3)
    document.add_paragraph("Установите соответствие между формулой и классом.")
    table = document.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "ФОРМУЛА"
    table.cell(0, 1).text = "КЛАСС"
    table.cell(1, 0).text = "А) HCl"
    table.cell(1, 1).text = "1) Кислота"
    table.cell(2, 0).text = "Б) NaOH"
    table.cell(2, 1).text = "2) Основание"
    _answer(document, "Соляная кислота и щёлочь.", "12")

    _task(document, 4)
    document.add_paragraph("Вычислите массовую долю в процентах.")
    _answer(document, "Считаем по формуле.", "0,25")

    _task(document, 5)
    document.add_paragraph("Расположите вещества в порядке возрастания массы.")
    _answer(document, None, "312")

    _task(document, 6)
    document.add_paragraph("Впишите название процесса.")
    _answer(document, "Переход из твёрдого состояния в газообразное.", "возгонка#сублимация")

    _task(document, 7)
    document.add_paragraph("Измерьте значение и запишите его с погрешностью.")
    _answer(document, None, "0,100,01")

    _task(document, 8)
    document.add_paragraph("Определите вещество по прибору.")
    document.add_picture(_png(), width=Inches(1))
    _answer(document, None, "42")

    document.save(str(path))


def build_repository(root: Path) -> Path:
    (root / "school" / "diagnostics").mkdir(parents=True)
    (root / "school" / "assets" / "questions").mkdir(parents=True)
    (root / "docs").mkdir()
    diagnostic = {
        "id": "oge-chemistry-1",
        "exam": "ОГЭ",
        "subject": "Химия",
        "mark": "9 класс",
        "quick_count": 1,
        "scoring": {"max_score": 100, "score_unit": "accuracy_percent"},
        "questions": [
            {
                "id": "seed1",
                "type": "input",
                "topic": "Периодический закон",
                "title": "Задание 4",
                "prompt": "Сколько протонов у углерода?",
                "max_primary_score": 1,
                "source": {
                    "provider": "maximum",
                    "official_year": 2026,
                    "approval_status": "draft",
                    "source_kind": "original",
                    "source_url": "https://maximumtest.ru/",
                    "exam_position": "4",
                    "rights_status": "original",
                    "verified_at": "2026-09-01",
                },
                "correct": ["6"],
            }
        ],
    }
    path = root / "school" / "diagnostics" / "oge-chemistry-1.json"
    path.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


@pytest.fixture()
def imported(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)
    importer.main([str(source_directory), "--root", str(tmp_path)])
    return tmp_path, catalog_path, source_directory


def _questions(catalog_path: Path) -> dict[str, dict]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {question["id"]: question for question in payload["questions"]}


def test_every_mapping_is_emitted_in_the_catalog_format(imported):
    _, catalog_path, _ = imported
    questions = _questions(catalog_path)

    single = questions["sp-chemistry-oge-2022-q1"]
    assert single["type"] == "single"
    assert [option["id"] for option in single["options"]] == ["a", "b", "c"]
    assert single["correct"] == "c"
    assert single["explanation"] == "Хлор стоит третьим в списке."

    multiple = questions["sp-chemistry-oge-2022-q2"]
    assert multiple["type"] == "multiple"
    assert multiple["selection_limit"] == 2
    assert multiple["correct"] == ["a", "c"]
    assert "explanation" not in multiple

    matching = questions["sp-chemistry-oge-2022-q3"]
    assert matching["type"] == "matching"
    assert [item["label"] for item in matching["items"]] == ["А) HCl", "Б) NaOH"]
    assert [option["id"] for option in matching["options"]] == ["o1", "o2"]
    assert matching["correct"] == {"i1": "o1", "i2": "o2"}
    assert "ФОРМУЛА" not in matching["prompt"]

    numeric = questions["sp-chemistry-oge-2022-q4"]
    assert numeric["type"] == "input"
    assert numeric["correct"] == ["0,25", "0.25"]

    sequence = questions["sp-chemistry-oge-2022-q5"]
    assert sequence["type"] == "input"
    assert sequence["correct"] == ["312"]
    assert sequence["prompt"].endswith(importer.SEQUENCE_HINT)

    text = questions["sp-chemistry-oge-2022-q6"]
    assert text["type"] == "text"
    assert text["correct"] == ["возгонка", "сублимация"]
    assert text["max_length"] == 80


def test_source_metadata_marks_editorial_drafts(imported):
    _, catalog_path, _ = imported
    source = _questions(catalog_path)["sp-chemistry-oge-2022-q1"]["source"]
    assert source == {
        "provider": "maximum_editorial",
        "official_year": 2022,
        "approval_status": "draft",
        "source_kind": "original",
        "source_url": "https://maximumtest.ru/",
        "rights_status": "original",
        "verified_at": source["verified_at"],
    }


def test_every_topic_is_a_placeholder_a_methodologist_still_has_to_map(imported):
    _, catalog_path, _ = imported

    for question in _questions(catalog_path).values():
        if not question["id"].startswith(importer.ID_PREFIX):
            continue
        expected = f"Задание {question['id'].rsplit('-q', 1)[1]}"
        assert question["topic"] == expected
        assert question["title"] == expected
        assert question["max_primary_score"] == 1
        assert "exam_position" not in question["source"]


def test_irregular_key_is_skipped_and_explained_in_the_report(imported):
    root, catalog_path, _ = imported
    assert "sp-chemistry-oge-2022-q7" not in _questions(catalog_path)
    report = (root / "authoring" / "sharepoint-import" / "report.md").read_text(
        encoding="utf-8"
    )
    assert SOURCE_NAME in report
    assert "Импортёр применяет только узкие" in report
    assert "источника с совпавшим SHA-256" in report
    assert "без правок" not in report
    assert "| 7 | skipped | - | irregular_key | 0 |" in report
    assert "| 1 | imported | single | - | 0 |" in report
    assert f"| {SOURCE_NAME} | 7 | - | irregular_key |" in report
    assert "## Темы, требующие сопоставления" in report


def test_inline_figure_becomes_a_deduplicated_question_asset(imported):
    root, catalog_path, _ = imported
    question = _questions(catalog_path)["sp-chemistry-oge-2022-q8"]
    assert question["asset"] == "assets/questions/sp-chemistry-oge-2022-q8-1.png"
    assert "assets" not in question
    asset = root / "school" / question["asset"]
    with Image.open(asset) as image:
        assert image.size == (40, 30)


def test_table_cell_figure_is_rejected_deterministically(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    document = Document()
    _task(document, 14)
    document.add_paragraph("Определите значение по рисунку.")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].add_run().add_picture(_png(), width=Inches(1))
    _answer(document, None, "42")
    source = source_directory / SOURCE_NAME
    document.save(source)

    root = tmp_path
    catalog_path = build_repository(root)
    importer.main([str(source_directory), "--root", str(root)])

    assert "sp-chemistry-oge-2022-q14" not in _questions(catalog_path)
    report = (root / "authoring" / "sharepoint-import" / "report.md").read_text(
        encoding="utf-8"
    )
    assert "| 14 | skipped | - | unsupported_table_cell_figure | 0 |" in report


def test_existing_questions_keep_their_exact_bytes(imported):
    _, catalog_path, _ = imported
    text = catalog_path.read_text(encoding="utf-8")
    assert '"id": "seed1"' in text
    assert '"correct": [\n        "6"\n      ]' in text
    assert json.loads(text)["questions"][0]["id"] == "seed1"
    assert json.loads(text)["quick_count"] == 1


def test_rerunning_the_import_replaces_only_the_prefixed_questions(imported):
    root, catalog_path, source_directory = imported
    before = catalog_path.read_bytes()
    assets_before = {
        path.name: path.read_bytes()
        for path in (root / "school" / "assets" / "questions").iterdir()
    }

    importer.main([str(source_directory), "--root", str(root)])

    assert catalog_path.read_bytes() == before
    assert {
        path.name: path.read_bytes()
        for path in (root / "school" / "assets" / "questions").iterdir()
    } == assets_before


def test_partial_import_preserves_unselected_questions_assets_and_report(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["questions"].extend(
        [
            {
                "id": "sp-chemistry-oge-2022-q1",
                "type": "input",
                "topic": "Старое задание",
                "title": "Старое задание",
                "prompt": "Старый выбранный вопрос",
                "answer_format": "number",
                "correct": ["1"],
                "max_primary_score": 1,
                "source": {"approval_status": "draft"},
            },
            {
                "id": "sp-chemistry-oge-2022-kisloty-q1",
                "type": "input",
                "topic": "Кислоты",
                "title": "Задание 1",
                "prompt": "Невыбранный вопрос",
                "answer_format": "number",
                "correct": ["2"],
                "max_primary_score": 1,
                "source": {"approval_status": "draft"},
            },
        ]
    )
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    target_before = importer.read_target(catalog_path)
    unselected_chunk = dict(target_before.chunks)["sp-chemistry-oge-2022-kisloty-q1"]

    assets_root = tmp_path / "school" / "assets" / "questions"
    selected_stale = assets_root / "sp-chemistry-oge-2022-q8-1.png"
    selected_stale.write_bytes(_png(8, 8).getvalue())
    unselected_asset = assets_root / "sp-chemistry-oge-2022-kisloty-q1-1.png"
    unselected_asset.write_bytes(_png(9, 9).getvalue())
    legacy_asset = assets_root / "legacy.png"
    legacy_asset.write_bytes(_png(10, 10).getvalue())
    report_path = tmp_path / "authoring" / "sharepoint-import" / "report.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("global report\n", encoding="utf-8")
    partial_report = tmp_path / "authoring" / "sharepoint-import" / "kir-223.md"

    importer.main(
        [
            str(source_directory),
            "--root",
            str(tmp_path),
            "--partial",
            "--report",
            "authoring/sharepoint-import/kir-223.md",
        ]
    )

    target_after = importer.read_target(catalog_path)
    after_chunks = dict(target_after.chunks)
    assert after_chunks["sp-chemistry-oge-2022-kisloty-q1"] == unselected_chunk
    identifiers = [key for key, _ in target_after.chunks]
    assert identifiers.index("sp-chemistry-oge-2022-q8") < identifiers.index(
        "sp-chemistry-oge-2022-kisloty-q1"
    )
    assert "sp-chemistry-oge-2022-q8" in identifiers
    assert "Старый выбранный вопрос" not in catalog_path.read_text(encoding="utf-8")
    assert unselected_asset.read_bytes() == _png(9, 9).getvalue()
    assert legacy_asset.read_bytes() == _png(10, 10).getvalue()
    assert selected_stale.read_bytes() != _png(8, 8).getvalue()
    assert report_path.read_text(encoding="utf-8") == "global report\n"
    partial_text = partial_report.read_text(encoding="utf-8")
    assert "частичного импорта" in partial_text
    assert "| 7 | skipped | - | irregular_key | 0 |" in partial_text
    assert all(
        importer.validate_question(question) is None
        for question in json.loads(catalog_path.read_text(encoding="utf-8"))["questions"]
        if question["id"].startswith("sp-chemistry-oge-2022-q")
    )

    catalog_before_repeat = catalog_path.read_bytes()
    assets_before_repeat = {
        path.name: path.read_bytes() for path in assets_root.iterdir()
    }
    report_before_repeat = partial_report.read_bytes()
    importer.main(
        [
            str(source_directory),
            "--root",
            str(tmp_path),
            "--partial",
            "--report",
            "authoring/sharepoint-import/kir-223.md",
        ]
    )
    assert catalog_path.read_bytes() == catalog_before_repeat
    assert {path.name: path.read_bytes() for path in assets_root.iterdir()} == assets_before_repeat
    assert partial_report.read_bytes() == report_before_repeat


def test_partial_import_requires_non_global_report(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    build_repository(tmp_path)

    with pytest.raises(SystemExit):
        importer.main([str(source_directory), "--root", str(tmp_path), "--partial"])

    with pytest.raises(SystemExit):
        importer.main(
            [
                str(source_directory),
                "--root",
                str(tmp_path),
                "--partial",
                "--report",
                str(tmp_path / "authoring" / "sharepoint-import" / "report.md"),
            ]
        )


def test_stale_prefixed_assets_are_removed_on_reimport(imported):
    root, _, source_directory = imported
    stale = root / "school" / "assets" / "questions" / "sp-old-question-1.png"
    stale.write_bytes(_png(8, 8).getvalue())
    kept = root / "school" / "assets" / "questions" / "legacy.png"
    kept.write_bytes(_png(8, 8).getvalue())

    importer.main([str(source_directory), "--root", str(root)])

    assert not stale.exists()
    assert kept.exists()


def test_dry_run_leaves_the_repository_untouched(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)
    before = catalog_path.read_bytes()

    importer.main([str(source_directory), "--root", str(tmp_path), "--dry-run"])

    assert catalog_path.read_bytes() == before
    assert not (tmp_path / "authoring").exists()


def test_repository_catalogs_round_trip_without_reformatting():
    for path in sorted((ROOT / "school" / "diagnostics").glob("*.json")):
        target = importer.read_target(path)
        rendered = importer.render_target(target, target.chunks)
        assert rendered == path.read_text(encoding="utf-8")


def test_the_import_never_shortens_the_full_diagnostic(imported):
    _, catalog_path, _ = imported
    document = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert "full_count" not in document
    assert document["questions"][0]["id"] == "seed1"
    assert len(document["questions"]) > 1


def test_the_repository_catalog_holds_only_sharepoint_questions():
    paths = sorted((ROOT / "school" / "diagnostics").glob("*.json"))
    assert paths

    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        # Every catalog pins `full_count`, so a later bank import cannot lengthen
        # the diagnostic. The leading questions stay the diagnostic; whatever a
        # topical package appends after them feeds the trainer and the daily plan.
        assert document["quick_count"] <= document["full_count"], path.name
        assert document["full_count"] <= len(document["questions"]), path.name
        assert all(
            question["id"].startswith(importer.ID_PREFIX)
            for question in document["questions"]
        ), path.name
        # The quick diagnostic asks eight questions, or the whole file when it
        # holds fewer than eight.
        assert document["quick_count"] == min(8, len(document["questions"])), path.name


def test_reordered_numeric_keys_become_accepted_input_variants():
    task = importer.SourceTask(number=1, answer=["1234#2134#1243#2143"])
    task.prompt_blocks.append("Заполните таблицу.")

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.correct == ("1234", "2134", "1243", "2143")
    assert payload.sequence is True


def test_table_gap_key_gets_sequence_metadata_from_source_shape():
    task = importer.SourceTask(
        number=20,
        prompt_tables=[importer.SourceTable(rows=(
            (("Железа",), ("Функция",), ("Изменения",)),
            (("(А)________",), ("Функция",), ("Давление",)),
            (("Поджелудочная",), ("(Б)________",), ("Голодание",)),
            (("Щитовидная",), ("Обмен",), ("(В)________",)),
        ))],
        prompt_blocks=[
            "1) Щитовидная железа",
            "2) Гипофиз",
            "3) Надпочечники",
            "4) Липидный обмен",
            "5) Углеводный обмен",
            "6) Обменные процессы",
        ],
        answer=["356"],
    )
    kind, payload = importer.classify(task)
    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "sequence"
    assert payload.answer_length == 3
    assert payload.allow_reuse is False
    assert payload.markers == ("А", "Б", "В")

    task.prompt_blocks.append("Цифры в ответе могут повторяться.")
    kind, payload = importer.classify(task)
    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.allow_reuse is True

    task.answer = ["35"]
    kind, payload = importer.classify(task)
    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "number"


def test_ordering_prompt_gets_sequence_metadata_without_catalog_override():
    task = importer.SourceTask(
        number=3,
        prompt_blocks=[
            "Расположите химические элементы в порядке ослабления металлических свойств.",
            "1) Калий;",
            "2) Алюминий;",
            "3) Литий.",
            "Запишите номера выбранных элементов в соответствующем порядке.",
        ],
        answer=["132"],
    )
    kind, payload = importer.classify(task)
    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "sequence"
    assert payload.answer_length == 3
    assert payload.markers == ("1", "2", "3")
    assert payload.allow_reuse is False


def test_ordering_prompt_reads_numbered_task_options():
    task = importer.SourceTask(
        number=8,
        prompt_blocks=[
            "Установите последовательность этапов процесса.",
            "Запишите последовательность цифр.",
        ],
        options=[
            "1) Первый этап.",
            "2) Второй этап.",
            "3) Третий этап.",
        ],
        answer=["312"],
    )

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "sequence"
    assert payload.answer_length == 3
    assert payload.allow_reuse is False
    assert payload.markers == ("1", "2", "3")


@pytest.mark.parametrize(
    ("source_name", "targets"),
    [
        (
            "ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx",
            {13: (2, True, ("А", "Б"))},
        ),
        (
            "ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx",
            {
                6: (2, False, ("А", "Б")),
                9: (2, False, ("А", "Б")),
                21: (4, False, ("1", "2", "3", "4")),
                23: (2, False, ("А", "Б")),
            },
        ),
        (
            "БИО_ЕГЭ_Диагностика_21-22_Заданий 21.docx",
            {8: (5, False, ("1", "2", "3", "4", "5"))},
        ),
    ],
)
def test_kir254_trusted_source_targets_build_explicit_sequence_contract(
    source_name: str, targets: dict[int, tuple[int, bool, tuple[str, ...]]]
):
    source = importer.read_source_file(
        ROOT / "authoring" / "sharepoint-authoring" / source_name
    )
    candidates, _ = importer.convert_file(source, "2026-09-04")
    questions = {candidate.task.number: candidate.question for candidate in candidates}

    for number, (answer_length, allow_reuse, markers) in targets.items():
        question = questions[number]
        task = next(task for task in source.tasks if task.number == number)
        assert all(option in question["prompt"] for option in task.options)
        assert question["answer_format"] == "sequence"
        assert question["answer_length"] == answer_length
        assert question["allow_reuse"] is allow_reuse
        assert question["markers"] == list(markers)
        trusted = replace(
            source, content_hash=importer.TRUSTED_SOURCE_HASHES[source.slug]
        )
        importer._repair_source_question(
            trusted, importer.SourceTask(number=number), question
        )
        assert question["topic"] == (
            importer.CHECKED_IN_TOPIC_MAP[source.slug][number]
        )

        untrusted = replace(trusted, content_hash="0" * 64)
        untouched = {"topic": f"Задание {number}"}
        importer._repair_source_question(
            untrusted, importer.SourceTask(number=number), untouched
        )
        assert untouched["topic"] == f"Задание {number}"


def test_ordering_prompt_can_read_a_numbered_choice_table():
    table = importer.SourceTable(rows=(
        (("1) Калий",), ("2) Алюминий",)),
        (("3) Литий",), ("4) Натрий",)),
    ))
    task = importer.SourceTask(
        number=3,
        prompt_blocks=[
            "Расположите элементы в порядке усиления металлических свойств.",
            "Запишите последовательность цифр.",
        ],
        prompt_tables=[table],
        answer=["2413"],
    )

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "sequence"
    assert payload.options == (("1", "Калий"), ("2", "Алюминий"), ("3", "Литий"), ("4", "Натрий"))


def test_numbered_table_without_ordering_prompt_stays_numeric():
    table = importer.SourceTable(rows=(
        (("1) Да",), ("2) Нет",)),
        (("3) Не указано",),),
    ))
    task = importer.SourceTask(
        number=3,
        prompt_blocks=["Выберите правильный вариант."],
        prompt_tables=[table],
        answer=["2"],
    )

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "number"


def test_lettered_ordering_prompt_gets_sequence_metadata_and_options():
    task = importer.SourceTask(
        number=4,
        prompt_blocks=[
            "В ответ запишите последовательность цифр, соответствующую буквам АБВГ.",
            "________ (А) ________ (Б) ________ (В) ________ (Г)",
            "Список слов:",
            "1) Сила Лоренца;",
            "2) Сила Кулона;",
            "3) Сила Ампера;",
            "4) Перпендикулярно;",
            "5) Параллельно;",
            "6) Электрический;",
            "7) Магнитный.",
        ],
        answer=["6714"],
    )
    kind, payload = importer.classify(task)
    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "sequence"
    assert payload.answer_length == 4
    assert payload.markers == ("А", "Б", "В", "Г")
    assert [marker for marker, _ in payload.options] == [str(index) for index in range(1, 8)]
    assert payload.allow_reuse is False


def test_numeric_prompt_with_sequence_footer_stays_number():
    task = importer.SourceTask(
        number=9,
        prompt_blocks=["Решите уравнение:", "Введите последовательность цифр без пробелов."],
        answer=["8"],
    )
    kind, payload = importer.classify(task)
    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "number"


def test_multi_digit_numeric_prompt_with_sequence_footer_stays_number():
    task = importer.SourceTask(
        number=13,
        prompt_blocks=[
            "Вычислите значение физической величины.",
            "Введите последовательность цифр без пробелов.",
        ],
        answer=["200"],
    )

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "number"
    assert payload.answer_length is None
    assert payload.allow_reuse is None


@pytest.mark.parametrize(
    ("catalog_file", "question_id", "answer_length", "markers", "key"),
    [
        ("oge-chemistry-192.json", "sp-chemistry-oge-2022-q3", 3, ("1", "2", "3"), "132"),
        ("oge-physics-197.json", "sp-physics-oge-2022-q4", 4, ("А", "Б", "В", "Г"), "6714"),
    ],
)
def test_real_catalog_ordering_prompts_regenerate_sequence_metadata(
    catalog_file: str,
    question_id: str,
    answer_length: int,
    markers: tuple[str, ...],
    key: str,
):
    document = json.loads(
        (ROOT / "school" / "diagnostics" / catalog_file).read_text(encoding="utf-8")
    )
    question = next(item for item in document["questions"] if item["id"] == question_id)
    task = importer.SourceTask(
        number=int(question["title"].split()[-1]),
        prompt_blocks=question["prompt"].splitlines(),
        answer=[key],
    )

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "sequence"
    assert payload.answer_length == answer_length
    assert payload.markers == markers
    assert payload.allow_reuse is False

    source = importer.SourceFile(
        Path(catalog_file), "ОГЭ", "subject", 2022, 1, (task,), topic="Тест",
    )
    rendered = importer.build_question(source, task, kind, payload, verified_at="2026-09-08")
    assert isinstance(rendered, dict)
    assert rendered["answer_format"] == "sequence"
    assert rendered["answer_length"] == answer_length
    assert rendered["markers"] == list(markers)
    assert rendered["allow_reuse"] is False


def test_numbered_choice_grid_renders_one_choice_per_line():
    """A 3×3 grid of numbered choices is a list, not a data table: the app must not
    draw a header row over "1) Основный оксид | 2) Кислая соль | 3) Амфотерный оксид"."""
    labels = [
        "1) Основный оксид", "2) Кислая соль", "3) Амфотерный оксид",
        "4) Кислота", "5) Средняя соль", "6) Кислота",
        "7) Гидроксид", "8) Несолеобразующий оксид", "9) Комплексная соль",
    ]
    table = importer.SourceTable(
        rows=tuple(tuple((label,) for label in labels[index:index + 3]) for index in range(0, 9, 3))
    )

    assert importer._render_table(table) == "\n".join(labels)


def test_duplicate_choice_labels_survive_the_import(tmp_path):
    """The source KIM lists «Кислота» twice on purpose; the catalog keeps all nine choices."""
    document = Document()
    _task(document, 5)
    document.add_paragraph("Установите соответствие между веществами и классами.")
    table = document.add_table(rows=3, cols=3)
    labels = [
        "1) Один", "2) Два", "3) Три",
        "4) Гидроксид", "5) Пять", "6) Гидроксид",
        "7) Кислота", "8) Восемь", "9) Девять",
    ]
    for cell, label in zip((cell for row in table.rows for cell in row.cells), labels):
        cell.text = label
    _answer(document, None, "277")
    source_path = tmp_path / "chemistry-grid.docx"
    document.save(source_path)

    task = importer.parse_document(source_path)[0]
    source = importer.SourceFile(
        source_path, "ЕГЭ", "chemistry", 2022, 28, (task,),
        content_hash=importer.TRUSTED_SOURCE_HASHES["chemistry-ege-2022"],
    )
    kind, payload = importer.classify(task)
    question = importer.build_question(source, task, kind, payload, verified_at="2026-09-01")
    importer._repair_source_question(source, task, question)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.answer_format == "sequence"
    assert [marker for marker, _ in payload.options] == [str(index) for index in range(1, 10)]
    assert "6) Гидроксид" in question["prompt"]
    assert "___" not in question["prompt"]


def test_stripping_leaves_the_source_punctuation_alone():
    """Only the full stop the cut clause took with it is restored; «!..» and «?..» in
    the source text are the author's and must survive untouched."""
    poem = "Облитый горечью и злостью!..\n(М. Ю. Лермонтов, 1840)\n— (29)А где?.. (30)Тут полбуханка была!"
    assert importer.strip_answer_sheet_instructions(poem) == poem
    assert importer.strip_answer_sheet_instructions(
        "Выберите верные утверждения. В ответ запишите цифры."
    ) == "Выберите верные утверждения."


def test_blank_answer_grid_rows_are_not_rendered():
    """«A | B | C | D» and «(А)____ | (Б)____» are the paper answer grid, not data."""
    grid = importer.SourceTable(rows=(
        (("A",), ("B",), ("C",), ("D",)),
        (("",), ("",), ("",), ("",)),
    ))
    assert importer._render_table(grid) == ""
    fill_in = importer.SourceTable(rows=(
        (("(А)______",), ("(Б)______",)),
    ))
    assert importer._render_table(fill_in) == ""
    xy = importer.SourceTable(rows=((("Х",), ("Y",)), (("",), ("",))))
    assert importer._render_table(xy) == ""
    data = importer.SourceTable(rows=(
        (("Вещество",), ("Формула",)),
        (("Кислород",), ("O2",)),
    ))
    assert importer._render_table(data) == "Вещество | Формула\nКислород | O2"


def test_stripping_the_table_instruction_keeps_the_sentence_end():
    stripped = importer.strip_answer_sheet_instructions(
        "К каждой позиции первого столбца подберите соответствующую позицию из второго столбца "
        "и запишите в таблицу выбранные цифры под соответствующими буквами."
    )
    assert stripped == (
        "К каждой позиции первого столбца подберите соответствующую позицию из второго столбца."
    )


def test_score_policy_approves_only_pinned_q05_and_biology_q18():
    q05_task = importer.SourceTask(number=5, prompt_blocks=["Назовите вещество."], answer=["7"])
    q05_source = importer.SourceFile(
        Path("chemistry.docx"), "ЕГЭ", "chemistry", 2022, 1, (q05_task,),
        content_hash=importer.TRUSTED_SOURCE_HASHES["chemistry-ege-2022"],
    )
    _, q05_payload = importer.classify(q05_task)
    q05 = importer.build_question(q05_source, q05_task, "input", q05_payload, verified_at="2026-09-01")
    importer._repair_source_question(q05_source, q05_task, q05)
    assert q05["max_primary_score"] == 1
    assert q05["source"]["approval_status"] == "approved"
    assert q05["source"]["exam_position"] == "5"

    biology_source = importer.SourceFile(
        Path("biology.docx"), "ЕГЭ", "biology", 2022, 1, (),
        content_hash=importer.TRUSTED_SOURCE_HASHES["biology-ege-2022"],
    )
    biology_task = importer.SourceTask(number=18)
    biology = {
        "max_primary_score": 1,
        "source": {
            "approval_status": "draft",
        },
    }
    importer._repair_source_question(biology_source, biology_task, biology)
    assert biology["max_primary_score"] == 2
    assert biology["source"] == {"approval_status": "approved", "exam_position": "18"}


def test_trusted_chemistry_sources_apply_the_official_position_topic_map():
    for slug, exam, expected in (
        ("chemistry-ege-2022", "ЕГЭ", "Окислительно-восстановительные реакции"),
        ("chemistry-oge-2022", "ОГЭ", "Окислительно-восстановительные реакции"),
    ):
        source = importer.SourceFile(
            Path(f"{slug}.docx"), exam, "chemistry", 2022, 1, (),
            content_hash=importer.TRUSTED_SOURCE_HASHES[slug],
        )
        question = {"topic": "Задание 19" if exam == "ЕГЭ" else "Задание 15"}
        importer._repair_source_question(source, importer.SourceTask(number=19 if exam == "ЕГЭ" else 15), question)
        assert question["topic"] == expected

        untrusted = importer.SourceFile(
            source.path, source.exam, source.subject_code, source.year, source.declared_tasks,
            (), content_hash="0" * 64,
        )
        question = {"topic": "Задание 15"}
        importer._repair_source_question(untrusted, importer.SourceTask(number=15), question)
        assert question["topic"] == "Задание 15"


def test_checked_in_topic_maps_cover_every_live_question():
    live_by_source: dict[str, set[int]] = {}
    topic_by_source: dict[str, dict[int, str]] = {}
    for catalog_path in (ROOT / "school" / "diagnostics").glob("*.json"):
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        for question in payload["questions"]:
            question_id = question["id"]
            if not question_id.startswith(importer.ID_PREFIX):
                continue
            source_slug, number = question_id[3:].rsplit("-q", 1)
            live_by_source.setdefault(source_slug, set()).add(int(number))
            if source_slug in importer.CHECKED_IN_TOPIC_MAP:
                topic_by_source.setdefault(source_slug, {})[int(number)] = question["topic"]

    assert set(importer.CHECKED_IN_TOPIC_MAP) == set(topic_by_source)
    for source_slug, checked_map in importer.CHECKED_IN_TOPIC_MAP.items():
        assert set(live_by_source[source_slug]) == set(checked_map)
        assert topic_by_source[source_slug] == checked_map
        assert all(not topic.startswith("Задание ") for topic in checked_map.values())


def test_topic_maps_have_matching_hash_and_evidence_guards():
    assert set(importer.CHECKED_IN_TOPIC_MAP) == set(importer.TRUSTED_SOURCE_HASHES)
    assert set(importer.CHECKED_IN_TOPIC_MAP) == set(importer.TOPIC_EVIDENCE_URLS)
    assert all(
        url.startswith(("https://doc.fipi.ru/", "https://koiro.edu.ru/", "https://co8a.ru/", "https://vpr-ege.ru/", "https://4ege.ru/"))
        for url in importer.TOPIC_EVIDENCE_URLS.values()
    )
    assert set(importer.TOPIC_EVIDENCE_MIRROR_URLS) <= set(importer.CHECKED_IN_TOPIC_MAP)
    assert importer.TOPIC_EVIDENCE_MIRROR_URLS["literature-ege-2022"] == (
        "https://co8a.ru/wp-content/uploads/2021/08/lis.pdf"
    )
    assert importer.TOPIC_EVIDENCE_URLS["mathematics-ege-2022"].endswith("ma-11-ege-2022-spets_prof.pdf")


def test_every_checked_in_topic_repair_is_hash_guarded_and_idempotent():
    for slug, checked_map in importer.CHECKED_IN_TOPIC_MAP.items():
        subject, exam_code, year = slug.rsplit("-", 2)
        exam = importer.EXAM_NAMES[exam_code]
        number = next(iter(checked_map))
        source = importer.SourceFile(
            Path(f"{slug}.docx"), exam, subject, int(year), len(checked_map), (),
            content_hash=importer.TRUSTED_SOURCE_HASHES[slug],
        )
        question = {
            "topic": f"Задание {number}",
            "prompt": "",
            "options": [],
            "source": {"approval_status": "draft"},
        }
        importer._repair_source_question(source, importer.SourceTask(number=number), question)
        first_repair = deepcopy(question)
        importer._repair_source_question(source, importer.SourceTask(number=number), question)
        assert question == first_repair
        assert question["topic"] == checked_map[number]

        untrusted = importer.SourceFile(
            source.path, source.exam, source.subject_code, source.year,
            source.declared_tasks, source.tasks, content_hash="0" * 64,
        )
        untouched = {
            "topic": f"Задание {number}",
            "prompt": "",
            "options": [],
            "source": {"approval_status": "draft"},
        }
        importer._repair_source_question(untrusted, importer.SourceTask(number=number), untouched)
        assert untouched["topic"] == f"Задание {number}"


def test_oge_math_target_repairs_punctuation_spacing_and_score():
    source = importer.SourceFile(
        Path("math.docx"), "ОГЭ", "mathematics", 2022, 19, (),
        content_hash=importer.TRUSTED_SOURCE_HASHES["mathematics-oge-2022"],
    )
    task = importer.SourceTask(number=6)
    question = {
        "prompt": "Вычислите значение .",
        "source": {"approval_status": "draft"},
    }

    importer._repair_source_question(source, task, question)

    assert question["prompt"] == "Вычислите значение."
    assert question["max_primary_score"] == 1
    assert question["source"]["approval_status"] == "approved"


@pytest.mark.parametrize("number, answer", [(6, "0,25"), (8, "13"), (9, "8"), (13, "1")])
def test_approved_oge_math_numeric_targets_have_explicit_number_format(number, answer):
    task = importer.SourceTask(number=number, prompt_blocks=["Вычислите значение."], answer=[answer])
    source = importer.SourceFile(
        Path("math.docx"), "ОГЭ", "mathematics", 2022, 19, (task,),
        content_hash=importer.TRUSTED_SOURCE_HASHES["mathematics-oge-2022"],
    )
    kind, payload = importer.classify(task)
    question = importer.build_question(source, task, kind, payload, verified_at="2026-09-01")
    importer._repair_source_question(source, task, question)

    assert question["answer_format"] == "number"
    assert question["max_primary_score"] == 1
    assert question["source"]["approval_status"] == "approved"


def test_changed_target_hash_gets_no_repair_or_approval():
    source = importer.SourceFile(
        Path("math.docx"), "ОГЭ", "mathematics", 2022, 19, (), content_hash="changed"
    )
    task = importer.SourceTask(number=6)
    question = {
        "prompt": "Вычислите значение .",
        "max_primary_score": 1,
        "source": {"approval_status": "draft"},
    }

    importer._repair_source_question(source, task, question)

    assert question["prompt"] == "Вычислите значение ."
    assert question["max_primary_score"] == 1
    assert question["source"] == {"approval_status": "draft"}


def test_packed_multi_digit_keys_are_still_skipped():
    task = importer.SourceTask(number=1, answer=["12#345"])
    task.prompt_blocks.append("Ответьте на два вопроса.")

    assert importer.classify(task) == ("skip", "irregular_key")


def test_unsupported_pdf_glyphs_are_normalized_instead_of_dropping_the_task():
    assert importer.clean_line("сто́л") == "стол"
    assert importer.clean_line("𝑚 · 𝑔") == "m · g"
    assert importer.clean_line("∠ABC") == "угол ABC"
    assert importer.renders(importer.clean_line("∠ABC = 30°"))


PLAN_SOURCE_NAME = "ХИМ_Кислоты_Заданий 8.docx"


def write_plan(path: Path, entries: list[dict]) -> Path:
    path.write_text(
        json.dumps({"sources": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return path


def plan_entry(source: Path, **overrides) -> dict:
    entry = {
        "path": f"/sites/x/{source.name}",
        "file_name": source.name,
        "content_hash": importer.file_digest(source),
        "subject": "chemistry",
        "exam": "oge",
        "season": "21-22",
        "topic": "Кислоты и основания",
        "topic_slug": "kisloty",
        "declared_question_count": 8,
    }
    entry.update(overrides)
    return entry


@pytest.fixture()
def planned(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    source = source_directory / PLAN_SOURCE_NAME
    build_source_document(source)
    catalog_path = build_repository(tmp_path)
    plan = write_plan(tmp_path / "plan.json", [plan_entry(source)])
    return tmp_path, catalog_path, source_directory, plan


def test_plan_supplies_subject_exam_year_and_topic(planned):
    root, catalog_path, source_directory, plan = planned

    importer.main([str(source_directory), "--plan", str(plan), "--root", str(root)])

    questions = _questions(catalog_path)
    single = questions["sp-chemistry-oge-2022-kisloty-q1"]
    assert single["type"] == "single"
    assert single["topic"] == "Кислоты и основания"
    assert single["title"] == "Задание 1"
    assert single["source"]["official_year"] == 2022


def test_plan_hash_mismatch_stops_the_import(planned):
    root, _, source_directory, _ = planned
    source = source_directory / PLAN_SOURCE_NAME
    plan = write_plan(
        root / "bad-plan.json", [plan_entry(source, content_hash="0" * 64)]
    )

    with pytest.raises(importer.ImportError, match="does not match the plan"):
        importer.main([str(source_directory), "--plan", str(plan), "--root", str(root)])


def test_a_file_outside_the_plan_keeps_its_filename_derived_id(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json",
        [plan_entry(source_directory / SOURCE_NAME, file_name="другой.docx")],
    )

    importer.main([str(source_directory), "--plan", str(plan), "--root", str(tmp_path)])
    with_plan = catalog_path.read_bytes()
    importer.main([str(source_directory), "--root", str(tmp_path)])

    assert catalog_path.read_bytes() == with_plan
    assert "sp-chemistry-oge-2022-q1" in _questions(catalog_path)


def test_colliding_ids_stop_the_import(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    build_source_document(source_directory / "ХИМ_ОГЭ_МРКТ_21-22_Заданий 8.docx")
    build_repository(tmp_path)

    with pytest.raises(importer.ImportError, match="Duplicate question ids"):
        importer.main([str(source_directory), "--root", str(tmp_path), "--dry-run"])


def test_a_numeric_key_may_end_with_a_full_stop():
    task = importer.SourceTask(number=1, answer=["1,84."])
    task.prompt_blocks.append("Вычислите плотность.")

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.correct == ("1,84", "1.84")


def test_an_explanation_paragraph_after_the_key_moves_to_the_solution(tmp_path):
    document = Document()
    _task(document, 1)
    document.add_paragraph("Вычислите массовую долю.")
    document.add_paragraph("Ответ:")
    document.add_paragraph("0,25")
    document.add_paragraph("Пояснение: делим массу вещества на массу раствора.")
    source = tmp_path / "explanation.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.answer == ["0,25"]
    assert task.solution == ["Пояснение: делим массу вещества на массу раствора."]


def test_open_answer_tasks_are_skipped_with_their_own_reason():
    task = importer.SourceTask(
        number=1,
        answer=["Развёрнутый ответ"],
        solution=["Критерии оценивания. Максимальный балл — 3."],
    )
    task.prompt_blocks.append("Обоснуйте ответ.")

    assert importer.classify(task) == ("skip", "open_answer")


def test_pdf_unsafe_degree_and_figure_dash_are_replaced():
    assert importer.clean_line("t = 30ᵒC") == "t = 30°C"
    assert importer.clean_line("5 ‒ 3") == "5 - 3"
    assert importer.renders(importer.clean_line("t = 30ᵒC"))


def test_base_diagnostic_questions_stay_ahead_of_bank_packages(tmp_path):
    """The leading questions are the diagnostic, so `full_count` keeps covering them."""
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    topical = source_directory / PLAN_SOURCE_NAME
    build_source_document(topical)
    catalog_path = build_repository(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json", [plan_entry(topical, season="20-21")]
    )

    importer.main([str(source_directory), "--plan", str(plan), "--root", str(tmp_path)])

    identifiers = [
        question["id"]
        for question in json.loads(catalog_path.read_text(encoding="utf-8"))["questions"]
        if question["id"].startswith(importer.ID_PREFIX)
    ]
    topical_start = min(
        index for index, identifier in enumerate(identifiers) if "kisloty" in identifier
    )
    assert all("kisloty" not in identifier for identifier in identifiers[:topical_start])
    assert identifiers[0] == "sp-chemistry-oge-2022-q1"


def _numbered_source(document, number: int, lines: list[str], *, leading: bool) -> None:
    """A task whose option list is typed as plain `N)` prompt lines."""
    _task(document, number)
    stem = "Укажите порядковый номер верного утверждения."
    blocks = lines + [stem] if leading else [stem] + lines
    for block in blocks:
        document.add_paragraph(block)


OPTION_LINES = ["1) Первое;", "2) Второе;", "3) Третье;", "4) Четвёртое."]


def test_a_trailing_numbered_block_becomes_the_option_list(tmp_path):
    document = Document()
    _numbered_source(document, 1, OPTION_LINES, leading=False)
    _answer(document, None, "3")
    source = tmp_path / "inline-options.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == ["Первое;", "Второе;", "Третье;", "Четвёртое."]
    assert task.prompt_blocks == ["Укажите порядковый номер верного утверждения."]
    assert importer.classify(task) == ("single", importer.SingleAnswerSpec((3,)))


def test_a_leading_numbered_block_becomes_the_option_list(tmp_path):
    """One editor typed the shared option list above the question stem."""
    document = Document()
    _numbered_source(document, 1, OPTION_LINES, leading=True)
    _answer(document, None, "2")
    source = tmp_path / "leading-options.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == ["Первое;", "Второе;", "Третье;", "Четвёртое."]
    assert task.prompt_blocks == ["Укажите порядковый номер верного утверждения."]
    assert importer.classify(task) == ("single", importer.SingleAnswerSpec((2,)))


def test_a_numbered_block_stays_in_the_prompt_when_the_key_orders_it(tmp_path):
    """`2314` reorders the four lines; they are not four answers to pick from."""
    document = Document()
    _numbered_source(document, 1, OPTION_LINES, leading=False)
    _answer(document, None, "2314")
    source = tmp_path / "ordering.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == []
    assert task.prompt_blocks[-1] == "4) Четвёртое."
    assert importer.classify(task)[0] == "input"


def test_a_numbered_block_stays_in_the_prompt_when_it_is_part_of_the_question(tmp_path):
    """A numbered list the prompt wraps on both sides is condition text."""
    document = Document()
    _task(document, 1)
    for block in ("Дан список величин.", *OPTION_LINES, "Сколько из них положительны?"):
        document.add_paragraph(block)
    _answer(document, None, "2")
    source = tmp_path / "mid-prompt.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == []
    assert len(task.prompt_blocks) == 6


def test_a_numbered_block_with_a_gap_is_not_an_option_list(tmp_path):
    document = Document()
    _numbered_source(document, 1, ["1) Первое;", "2) Второе;", "4) Четвёртое."], leading=False)
    _answer(document, None, "2")
    source = tmp_path / "gap.docx"
    document.save(str(source))

    assert importer.parse_document(source)[0].options == []


def test_two_numbered_lines_are_too_few_to_be_an_option_list(tmp_path):
    document = Document()
    _numbered_source(document, 1, ["1) Первое;", "2) Второе."], leading=False)
    _answer(document, None, "2")
    source = tmp_path / "pair.docx"
    document.save(str(source))

    assert importer.parse_document(source)[0].options == []


def test_a_single_digit_key_carries_no_sequence_hint():
    task = importer.SourceTask(number=1, answer=["3"])
    task.prompt_blocks.append("Сколько молекул участвует в реакции?")

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.sequence is False


def test_a_multi_digit_key_still_carries_the_sequence_hint():
    task = importer.SourceTask(number=1, answer=["134"])
    task.prompt_blocks.append("Выпишите номера верных утверждений.")

    payload = importer.classify(task)[1]
    assert isinstance(payload, importer.InputAnswerSpec)
    assert payload.sequence is True


def _english_source() -> importer.SourceFile:
    return importer.SourceFile(
        path=Path("АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx"),
        exam="ЕГЭ",
        subject_code="english-language",
        year=2022,
        declared_tasks=23,
        tasks=(),
    )


def _word_formation(key: str, hint: str) -> importer.SourceTask:
    task = importer.SourceTask(number=12, answer=[key])
    task.prompt_blocks.append("Преобразуйте слово так, чтобы оно подошло по смыслу.")
    task.prompt_blocks.append(f"12 | Apollo ________ by her grace. | {hint}")
    return task


def test_a_glued_multi_word_key_is_skipped_instead_of_shipping_unanswerable(tmp_path):
    for key, hint in (("wasimpressed", "IMPRESS"), ("didnotbelieve", "NOT BELIEVE")):
        task = _word_formation(key, hint)
        kind, payload = importer.classify(task)
        assert kind == "text"
        assert importer.build_question(
            _english_source(), task, kind, payload, verified_at="2026-09-04"
        ) == "glued_answer"


def test_a_regular_word_formation_key_still_ships(tmp_path):
    for key, hint in (("greatest", "GREAT"), ("unbelievable", "BELIEVE"), ("women", "WOMAN")):
        task = _word_formation(key, hint)
        kind, payload = importer.classify(task)
        question = importer.build_question(
            _english_source(), task, kind, payload, verified_at="2026-09-04"
        )
        assert question["correct"] == [key]


def test_text_metadata_and_stress_are_inferred_only_from_verified_shapes():
    assert importer.load_answer_variants(ROOT / "authoring" / "answer-variants.json") == {
        "sp-russian-language-ege-2022-q14": ["вскоре потому"]
    }
    english_source = _english_source()
    english_task = _word_formation("greatest", "GREAT")
    english_prompt = importer.build_prompt(english_task)
    assert importer._text_metadata(english_source, english_prompt) == {
        "answer_format": "word",
        "lang": "en",
    }

    russian_source = importer.SourceFile(
        Path("РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx"),
        "ЕГЭ", "russian-language", 2022, 26, (),
    )
    russian_task = importer.SourceTask(
        number=14,
        prompt_blocks=[
            "Определите предложение, в котором оба выделенных слова пишутся СЛИТНО. "
            "Раскройте скобки и выпишите эти два слова."
        ],
    )
    assert importer._text_metadata(russian_source, importer.build_prompt(russian_task)) == {
        "answer_format": "words",
        "lang": "ru",
    }

    stress_task = importer.SourceTask(
        number=4,
        prompt_blocks=[
            "В одном из приведённых ниже слов допущена ошибка в постановке ударения: "
            "НЕВЕРНО выделена буква, обозначающая ударный гласный звук."
        ],
        options=["ПартЕр", "ПозвонИт", "ЭлектропровОд", "ВероисповЕдание", "ЖалюзИ"],
    )
    converted = importer._stress_options(russian_source, stress_task)
    assert converted is not None
    assert converted[2] == {"label": "электропровод", "stress": "электропрово\u0301д"}

    negative = importer.SourceTask(
        number=5,
        prompt_blocks=["Выпишите слово, выделенное заглавными буквами."],
        options=["ПАРТЕР", "ПОЗВОНИТ"],
    )
    assert importer._stress_options(russian_source, negative) is None


def test_tracked_russian_q04_docx_rebuilds_all_stress_options():
    source_path = ROOT / "authoring" / "sharepoint-authoring" / "РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx"
    source = importer.read_source_file(source_path)
    task = next(task for task in importer.parse_document(source_path) if task.number == 4)

    assert task.answer == ["3"]
    kind, payload = importer.classify(task)
    assert kind == "single"
    question = importer.build_question(source, task, kind, payload, verified_at="2026-09-04")

    assert isinstance(question, dict)
    assert question["correct"] == "c"
    assert [option["label"] for option in question["options"]] == [
        "партер", "позвонит", "электропровод", "вероисповедание", "жалюзи",
    ]
    assert [option["stress"] for option in question["options"]] == [
        "парте\u0301р", "позвони\u0301т", "электропрово\u0301д",
        "вероиспове\u0301дание", "жалюзи\u0301",
    ]


def test_verified_at_can_be_pinned_to_a_given_day(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)

    importer.main(
        [str(source_directory), "--root", str(tmp_path), "--verified-at", "2026-09-04"]
    )

    questions = _questions(catalog_path)
    imported_questions = [
        question
        for identifier, question in questions.items()
        if identifier.startswith(importer.ID_PREFIX)
    ]
    assert imported_questions
    assert all(
        question["source"]["verified_at"] == "2026-09-04"
        for question in imported_questions
    )


def test_a_matching_table_labelled_with_dots_becomes_a_matching_question():
    """Editors label the two columns with a dot as often as with a bracket."""
    table = importer.SourceTable(rows=(
        (("События",), ("Годы",)),
        (("А. Первое событие",), ("1. 1185 г.",)),
        (("Б. Второе событие",), ("2. 1825 г.",)),
        (("B. Третье событие",), ("3. 1613 г.",)),
        ((), ("4. 1762 г.",)),
    ))
    task = importer.SourceTask(
        number=1,
        prompt_blocks=["Установите соответствие."],
        prompt_tables=[table],
        answer=["213"],
    )

    kind, payload = importer.classify(task)

    assert kind == "matching"
    # The third row is labelled with a Latin B that looks like the Cyrillic one.
    assert isinstance(payload, importer.MatchingAnswerSpec)
    assert len(payload.items) == 3
    assert [digit for digit, _ in payload.options] == ["1", "2", "3", "4"]


def test_an_unreadable_matching_table_is_skipped_instead_of_flattened():
    """A table the converter cannot read renders as `left | right` noise."""
    table = importer.SourceTable(rows=(
        (("Величины",), ("Значения",)),
        (("Первый пункт без буквы",), ("1) Первое",)),
        (("Б) Второй пункт",), ("2) Второе",)),
        ((), ("3) Третье",)),
    ))
    task = importer.SourceTask(
        number=1,
        prompt_blocks=["Установите соответствие."],
        prompt_tables=[table],
        answer=["12"],
    )
    kind, payload = importer.classify(task)
    assert kind == "input"

    question = importer.build_question(
        importer.SourceFile(Path("f.docx"), "ЕГЭ", "physics", 2022, 1, ()),
        task, kind, payload, verified_at="2026-09-04",
    )

    assert importer._rejection(question, []) == "unreadable_matching"


def test_answer_sheet_instructions_leave_the_prompt_the_app_collects():
    """The Mini App collects the answer, so telling the student where to write it lies."""
    stripped = importer.strip_answer_sheet_instructions(
        "Установите соответствие между событиями и годами.\n"
        "В ответ запишите последовательность цифр, соответствующую буквам АБВ."
    )
    assert stripped == "Установите соответствие между событиями и годами."

    # The sentence survives without its full stop in some documents.
    assert importer.strip_answer_sheet_instructions(
        "Подберите позицию второго столбца.\nВ ответ запишите последовательность цифр"
    ) == "Подберите позицию второго столбца."

    # A task that is genuinely about writing a measurement keeps its wording.
    kept = "Запишите результат измерения напряжения с учётом погрешности."
    assert importer.strip_answer_sheet_instructions(kept) == kept


def test_option_labels_drop_the_list_punctuation_of_their_source():
    assert importer._option_label("Реформация в Германии;") == "Реформация в Германии"
    assert importer._option_label("вторая позиция,") == "вторая позиция"
    assert importer._option_label("обычный вариант") == "обычный вариант"


def test_a_matching_task_keeps_the_data_table_it_reasons_about():
    """Only the table that became the pairs is dropped from the prompt."""
    data = importer.SourceTable(rows=(
        (("Статья",), ("Доля",)),
        (("На армию",), ("40 %",)),
        (("На флот",), ("10 %",)),
    ))
    pairs = importer.SourceTable(rows=(
        (("Начала",), ("Завершения",)),
        (("А) Расходы на армию",), ("1) Составляли более половины.",)),
        (("Б) Расходы на флот",), ("2) Были меньше десятой части.",)),
    ))
    task = importer.SourceTask(
        number=7,
        prompt_blocks=["Используя данные таблицы, завершите суждения."],
        prompt_tables=[data, pairs],
        answer=["12"],
    )

    kind, payload = importer.classify(task)
    assert kind == "matching"

    question = importer.build_question(
        importer.SourceFile(Path("f.docx"), "ОГЭ", "history", 2022, 1, ()),
        task, kind, payload, verified_at="2026-09-04",
    )

    assert "На армию | 40 %" in question["prompt"]
    assert "Составляли более половины" not in question["prompt"]


def test_the_editor_can_add_an_accepted_wording_that_survives_a_reimport(tmp_path):
    """A wording typed into the catalog would be lost on the next run; this file is not."""
    variants = tmp_path / "answer-variants.json"
    variants.write_text(
        json.dumps({"variants": {"sp-chemistry-oge-2022-q1": ["иное название"]}}),
        encoding="utf-8",
    )

    loaded = importer.load_answer_variants(variants)
    assert loaded == {"sp-chemistry-oge-2022-q1": ["иное название"]}

    question = {"id": "q", "type": "text", "correct": ["ответ"]}
    assert importer.apply_answer_variants(question, ["Ответ.", "иное название"]) is None
    # The first wording only differs by case and a full stop, so it adds nothing.
    assert question["correct"] == ["ответ", "иное название"]


def test_an_accepted_wording_needs_a_free_text_question():
    question = {"id": "q", "type": "single", "correct": "a"}
    assert importer.apply_answer_variants(question, ["что-то"]) == (
        "answer_variants_need_a_text_question"
    )


def test_a_malformed_answer_variants_file_stops_the_import(tmp_path):
    path = tmp_path / "answer-variants.json"
    path.write_text(json.dumps({"variants": {"q": []}}), encoding="utf-8")
    with pytest.raises(importer.ImportError):
        importer.load_answer_variants(path)

    path.write_text(json.dumps({"variants": {"q": ["x" * 200]}}), encoding="utf-8")
    with pytest.raises(importer.ImportError):
        importer.load_answer_variants(path)

    path.write_text(json.dumps({"variants": {"q": ["..."]}}), encoding="utf-8")
    with pytest.raises(importer.ImportError):
        importer.load_answer_variants(path)

    path.write_text(
        json.dumps({"variants": {"q": ["Ответ", " ОТВЕТ. "]}}),
        encoding="utf-8",
    )
    with pytest.raises(importer.ImportError):
        importer.load_answer_variants(path)

    assert importer.load_answer_variants(tmp_path / "missing.json") == {}

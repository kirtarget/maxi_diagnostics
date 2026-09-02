from __future__ import annotations

import heapq
import itertools
import json
import math
from pathlib import Path


CATALOG_PATH = Path(__file__).parents[1] / "school" / "diagnostics" / "oge-informatics-466.json"
OFFICIAL_CRITERIA_URL = (
    "https://doc.fipi.ru/oge/demoversii-specifikacii-kodifikatory/2026/inf_9_2026.zip"
)
EXPECTED_POSITIONS = {
    "q3889": 1,
    "q3888": 2,
    "q3892": 3,
    "q3893": 4,
    "q3896": 5,
    "q3898": 6,
    "q3899": 7,
    "q3901": 8,
    "q3904": 9,
    "q3905": 10,
    "q3909": 12,
}


def _catalog_questions() -> list[dict[str, object]]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return payload["questions"]


def _answer(question: dict[str, object]) -> str:
    correct = question["correct"]
    assert isinstance(correct, list) and len(correct) == 1
    return str(correct[0])


def _decode_prefix_code(bits: str, codes: dict[str, str]) -> str:
    by_code = {code: symbol for symbol, code in codes.items()}
    decoded: list[str] = []
    cursor = ""
    for bit in bits:
        cursor += bit
        if cursor in by_code:
            decoded.append(by_code[cursor])
            cursor = ""
    assert cursor == ""
    return "".join(decoded)


def _shortest_path(edges: list[tuple[str, str, int]], start: str, finish: str) -> int:
    graph: dict[str, list[tuple[str, int]]] = {}
    for left, right, weight in edges:
        graph.setdefault(left, []).append((right, weight))
        graph.setdefault(right, []).append((left, weight))
    queue: list[tuple[int, str]] = [(0, start)]
    best = {start: 0}
    while queue:
        distance, vertex = heapq.heappop(queue)
        if vertex == finish:
            return distance
        if distance != best[vertex]:
            continue
        for neighbor, weight in graph[vertex]:
            candidate = distance + weight
            if candidate < best.get(neighbor, math.inf):
                best[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    raise AssertionError("finish is unreachable")


def _count_directed_paths(edges: list[tuple[str, str]], order: list[str], start: str, finish: str) -> int:
    counts = {vertex: 0 for vertex in order}
    counts[start] = 1
    outgoing: dict[str, list[str]] = {}
    for left, right in edges:
        outgoing.setdefault(left, []).append(right)
    for vertex in order:
        for neighbor in outgoing.get(vertex, []):
            counts[neighbor] += counts[vertex]
    return counts[finish]


def _to_base(number: int, base: int) -> str:
    digits: list[str] = []
    while number:
        number, digit = divmod(number, base)
        digits.append(str(digit))
    return "".join(reversed(digits)) or "0"


def _run_executor(start: int, commands: tuple[int, ...]) -> int:
    value = start
    for command in commands:
        value = value + 3 if command == 1 else value * 2
    return value


def test_oge_informatics_draft_preserves_ids_positions_and_original_rights() -> None:
    questions = _catalog_questions()

    pilot_questions = questions[:len(EXPECTED_POSITIONS)]
    assert [question["id"] for question in pilot_questions] == list(EXPECTED_POSITIONS)
    assert all("asset" not in question and "assets" not in question for question in pilot_questions)
    assert all("disk.yandex" not in str(question).lower() for question in pilot_questions)

    for question in pilot_questions:
        position = EXPECTED_POSITIONS[str(question["id"])]
        source = question["source"]
        assert question["title"] == f"Задание {position}"
        assert question["max_primary_score"] == 1
        assert isinstance(question["explanation"], str) and len(question["explanation"]) >= 80
        assert source == {
            "provider": "maximum",
            "official_year": 2026,
            "approval_status": "draft",
            "source_kind": "original",
            "source_url": "https://maximumtest.ru/",
            "exam_position": str(position),
            "official_criteria_url": OFFICIAL_CRITERIA_URL,
            "rights_status": "original",
            "verified_at": "2026-09-01",
        }


def test_oge_informatics_answers_are_reproduced_by_independent_algorithms() -> None:
    questions = {str(question["id"]): question for question in _catalog_questions()}

    expected = {
        "q3889": str(160 * math.ceil(math.log2(64)) // 8),
        "q3888": _decode_prefix_code(
            "0101101110110",
            {"1": "0", "2": "10", "3": "110", "4": "111"},
        ),
        "q3892": str(sum(1 for x in range(1, 30) if x >= 3 and x < 9 and x != 5)),
        "q3893": str(_shortest_path(
            [
                ("A", "B", 4),
                ("A", "C", 2),
                ("C", "B", 1),
                ("B", "D", 5),
                ("C", "D", 8),
                ("C", "E", 10),
                ("D", "E", 2),
            ],
            "A",
            "E",
        )),
        "q3896": str(_run_executor(7, (1, 2, 1, 2))),
        "q3898": str(sum(i * i if i % 2 == 0 else i for i in range(1, 7))),
        "q3899": next(
            "".join(str(index + 1) for index in order)
            for order in itertools.permutations(range(4))
            if "".join(["168.", "192.", "25", ".7"][index] for index in order)
            == "192.168.25.7"
        ),
        "q3901": str(420 + 310 - 590),
        "q3904": str(_count_directed_paths(
            [
                ("S", "A"),
                ("S", "B"),
                ("B", "A"),
                ("A", "C"),
                ("A", "D"),
                ("B", "D"),
                ("D", "C"),
                ("C", "T"),
                ("D", "T"),
            ],
            ["S", "B", "A", "D", "C", "T"],
            "S",
            "T",
        )),
        "q3905": _to_base(345, 8),
        "q3909": str(sum(
            size
            for name, size in [
                ("task_01.txt", 14),
                ("task_02.txt", 9),
                ("task_notes.docx", 30),
                ("task_03.txt", 17),
                ("archive_task.txt", 50),
                ("task_04.png", 21),
            ]
            if name.startswith("task_") and name.endswith(".txt")
        )),
    }

    assert {
        question_id: _answer(questions[question_id]) for question_id in expected
    } == expected

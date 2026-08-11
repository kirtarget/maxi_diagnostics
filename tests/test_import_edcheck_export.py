from scripts.import_edcheck_export import (
    _convert_question,
    _explanation,
    _inline_image_sources,
    _image_extension,
    _materialize_diagnostics_assets,
    _mathml_text,
    _prompt,
)
from scripts import import_edcheck_export


def test_importer_preserves_clean_bounded_explanation():
    converted = _convert_question({
        "question_id": 7,
        "question_index": 1,
        "description_text": "Чему равно 2 + 2?",
        "description_html": "",
        "images": [],
        "audio_file": None,
        "subject": {"code": "math"},
        "blocks": [],
        "type": "short-answer",
        "correct_answers": ["4"],
        "solution": "Сложите два и два: получится четыре.",
    })

    assert converted is not None
    assert converted["explanation"] == "Сложите два и два: получится четыре."


def test_importer_drops_blank_or_oversized_explanation():
    assert _explanation({"solution": "   "}) is None
    assert _explanation({"solution": "x" * 2001}) is None


def test_importer_accepts_a_cleaned_explanation_at_the_exact_limit():
    explanation = "x" * 2000

    assert _explanation({"solution": f" \r\n{explanation}\t\r"}) == explanation


def test_explanation_uses_supported_alias_priority_and_plain_strings_only():
    assert _explanation({
        "solution": "Первый источник",
        "answer_explanation": "Второй источник",
        "explanation": "Третий источник",
    }) == "Первый источник"
    assert _explanation({
        "solution": {"html": "не строка"},
        "answer_explanation": "Второй источник",
        "explanation": "Третий источник",
    }) == "Второй источник"


def test_mathml_text_preserves_powers_and_operators():
    mathml = """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <msup><mn>6</mn><mrow><mn>3</mn><mo>−</mo><mi>x</mi></mrow></msup>
      <mo>=</mo><mn>0</mn><mo>,</mo><mn>6</mn><mo>·</mo>
      <msup><mn>10</mn><mrow><mn>3</mn><mo>−</mo><mi>x</mi></mrow></msup>
    </math>"""
    assert _mathml_text(mathml) == "6^(3−x)=0,6·10^(3−x)"


def test_prompt_prefers_mathml_over_flattened_export_text():
    mathml = (
        "&lt;math xmlns=&quot;http://www.w3.org/1998/Math/MathML&quot;&gt;"
        "&lt;msup&gt;&lt;mn&gt;2&lt;/mn&gt;&lt;mi&gt;x&lt;/mi&gt;&lt;/msup&gt;"
        "&lt;mo&gt;=&lt;/mo&gt;&lt;mn&gt;8&lt;/mn&gt;&lt;/math&gt;"
    )
    question = {
        "description_text": "Решите уравнение: 2 x = 8",
        "description_html": (
            f'<p>Решите уравнение:</p><span data-mathml="{mathml}">'
            "<span><math><mn>2</mn></math></span></span>"
        ),
        "images": [],
        "audio_file": None,
    }
    assert _prompt(question) == "Решите уравнение:\n2^(x)=8"


def test_prompt_keeps_text_and_extracts_inline_images_when_export_list_is_empty():
    question = {
        "description_text": "Match the numbered structures in the figure.",
        "description_html": (
            '<p>Match the numbered structures in the figure.</p>'
            '<img src="https://storage.yandexcloud.net/bucket/question.png">'
            '<img src="data:image/png;base64,iVBORw0KGgo=">'
        ),
        "images": [],
        "audio_file": None,
    }

    assert _prompt(question) == "Match the numbered structures in the figure."
    assert _inline_image_sources(question) == (
        "https://storage.yandexcloud.net/bucket/question.png",
        "data:image/png;base64,iVBORw0KGgo=",
    )


def test_materialize_diagnostics_assets_preserves_all_source_images(tmp_path):
    remote = b"\xff\xd8\xff\xe0test-jpeg"
    diagnostics = [
        (
            "demo.json",
            {
                "questions": [
                    {
                        "id": "q123",
                        "_asset_sources": [
                            "data:image/png;base64,iVBORw0KGgo=",
                            "https://storage.yandexcloud.net/bucket/question.jpg",
                        ],
                    }
                ]
            },
        )
    ]
    asset_directory = tmp_path / "assets" / "questions"
    asset_directory.mkdir(parents=True)

    _materialize_diagnostics_assets(
        diagnostics,
        asset_directory,
        fetch_remote=lambda _source: remote,
    )

    question = diagnostics[0][1]["questions"][0]
    assert question == {
        "id": "q123",
        "assets": [
            "assets/questions/q123-1.png",
            "assets/questions/q123-2.jpg",
        ],
    }
    assert (asset_directory / "q123-1.png").read_bytes().startswith(b"\x89PNG")
    assert (asset_directory / "q123-2.jpg").read_bytes() == remote


def test_image_extension_recognizes_svg_returned_by_formula_service():
    payload = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"/>'
    )

    assert _image_extension(payload) == ".svg"


def test_remote_image_download_retries_a_transient_timeout(monkeypatch):
    attempts = 0
    payload = b"\x89PNG\r\n\x1a\nimage"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def geturl(self):
            return "https://storage.yandexcloud.net/bucket/question.png"

        def read(self, _limit):
            return payload

    def flaky_urlopen(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary timeout")
        return Response()

    monkeypatch.setattr(import_edcheck_export, "urlopen", flaky_urlopen)

    assert import_edcheck_export._download_remote_image(
        "https://storage.yandexcloud.net/bucket/question.png"
    ) == payload
    assert attempts == 2

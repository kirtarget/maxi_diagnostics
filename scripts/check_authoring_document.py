"""Check an authoring document against ``docs/AUTHORING_TEMPLATE.md``.

Names every task and field that is wrong and changes nothing.

    python scripts/check_authoring_document.py <файл.docx> [<файл.docx> ...]

Exit status is 1 when any document has a problem.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from authoring_document import check_document, read_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documents", nargs="+", type=Path)
    arguments = parser.parse_args(argv)
    failed = False
    for path in arguments.documents:
        problems = check_document(read_document(path))
        prefix = f"{path.name}: " if len(arguments.documents) > 1 else ""
        if not problems:
            print(f"{prefix}ошибок нет")
            continue
        failed = True
        for problem in problems:
            print(f"{prefix}{problem}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

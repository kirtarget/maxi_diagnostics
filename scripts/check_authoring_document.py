"""Check a document written in the authoring format and change nothing.

The editor runs this before handing a document over. It names the task and the
field that need fixing, in document order, and says nothing else.

    python scripts/check_authoring_document.py <файл.docx> [<файл.docx> ...]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from authoring_document import check_authoring_document, read_authoring_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documents", nargs="+", type=Path, help="Документы для проверки")
    arguments = parser.parse_args(argv)

    failed = False
    for path in arguments.documents:
        if not path.is_file():
            print(f"НЕТ ФАЙЛА {path}")
            failed = True
            continue
        errors = check_authoring_document(path)
        if errors:
            failed = True
            print(f"ОШИБКИ {path}")
            for error in errors:
                print(f"  {error}")
            continue
        document = read_authoring_document(path)
        print(f"OK {path}: {len(document.tasks)} заданий")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

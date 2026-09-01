#!/usr/bin/env python3
"""Reapply the shared shell to the demo cards.

The cards are hand-written. Each one is a run sheet for a live demo — what to
type, what to click, what to say — and the wording is the point of it, so it
does not come out of a template.

What *is* shared is the shell: the fonts, the palette, the copy-to-clipboard
behaviour, and the charset declaration. That lives in `_template.html`, and
this script splices it back around each card's content without touching the
content itself.

    python3 docs/cards/build.py

Run it after editing `_template.html`. Editing a card means editing the card.
"""

from __future__ import annotations

import pathlib
import re

HERE = pathlib.Path(__file__).parent
TEMPLATE = (HERE / "_template.html").read_text()


def title_of(src: str) -> str:
    m = re.search(r"<title>(.*?)</title>", src, re.S)
    return m.group(1) if m else "Demo Card"


def restyle(path: pathlib.Path) -> None:
    src = path.read_text()
    body = src.split("</style>", 1)[1].rsplit("<script>", 1)[0].strip()
    path.write_text(TEMPLATE.replace("__TITLE__", title_of(src))
                            .replace("__CONTENT__", body))


def main() -> None:
    for path in sorted(HERE.glob("*.html")):
        if path.name.startswith("_"):
            continue
        restyle(path)
        print(f"  restyled {path.name}")


if __name__ == "__main__":
    main()

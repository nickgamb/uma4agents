#!/usr/bin/env python3
"""Publish the demo cards as site pages.

The card is the source. This renders each one into
site/src/pages/docs/guides/, as the same two tables the card shows, so a page
cannot drift from the run sheet it is supposed to be.

    python3 docs/cards/to-docs.py
"""

from __future__ import annotations

import html
import pathlib
import re

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent.parent / "site" / "src" / "pages" / "docs" / "guides"

# slug -> (page title, seo title, description, next links)
PAGES = {
    "kagent-demo": (
        "Alice to Bob",
        "Demo an unmodified agent framework held to an owner's policy",
        "An agent framework nobody modified, asking for an owner's holdings, "
        "and her deciding each request from her own portal.",
        [("Two owners, one account", "/docs/guides/demo-joint-account/"),
         ("Her own agent", "/docs/guides/demo-her-own-agent/")],
    ),
    "joint-ownership": (
        "Two owners, one account",
        "Demo a jointly held account neither owner can release alone",
        "A joint account where both holders are asked and either can stop it.",
        [("Two owners, two authorities", "/docs/guides/demo-two-authorities/"),
         ("Joint ownership", "/docs/overview/joint-ownership/")],
    ),
    "multi-owner": (
        "Two owners, two authorities",
        "Demo two owners answering the same agent differently",
        "One agent and one key against two owners, who answer differently.",
        [("The firm's book", "/docs/guides/demo-the-firms-book/"),
         ("Many owners, one resource server", "/docs/overview/multi-owner/")],
    ),
    "first-party": (
        "Her own agent",
        "Demo a first-party agent held to the same ceiling as a stranger",
        "One rule and one tier, with an agent she operates and one she does not.",
        [("Her personal AI", "/docs/guides/demo-personal-ai/"),
         ("Her own agent", "/docs/overview/first-party/")],
    ),
    "personal-ai": (
        "Her personal AI",
        "Demo standing consent answering for an owner who is asleep",
        "pAI-OS answering from standing consent, and refusing what it cannot "
        "ask her about.",
        [("The firm's book", "/docs/guides/demo-the-firms-book/"),
         ("Put the authority on her device", "/docs/guides/personal-authority/")],
    ),
    "organization": (
        "The firm's book",
        "Demo an organization sharing a resource a member administers",
        "A resource that exists in a member's authority only while she is a "
        "member.",
        [("Two owners, one account", "/docs/guides/demo-joint-account/"),
         ("Shared ownership", "/docs/overview/shared-ownership/")],
    ),
}

SLUG = {"kagent-demo": "demo-alice-to-bob",
        "joint-ownership": "demo-joint-account",
        "multi-owner": "demo-two-authorities",
        "first-party": "demo-her-own-agent",
        "personal-ai": "demo-personal-ai",
        "organization": "demo-the-firms-book"}


def text(fragment: str) -> str:
    """Card HTML to markdown-safe inline text, keeping bold and code."""
    s = fragment
    s = re.sub(r"<code[^>]*>(.*?)</code>", lambda m: f"`{strip(m.group(1))}`", s, flags=re.S)
    s = re.sub(r"<strong>(.*?)</strong>", lambda m: f"**{strip(m.group(1))}**", s, flags=re.S)
    s = re.sub(r"<em>(.*?)</em>", lambda m: f"*{strip(m.group(1))}*", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip().replace("|", "\\|")


def strip(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def cell_command(fragment: str) -> str:
    """A command block as one table cell — newlines become <br>."""
    lines = [l for l in html.unescape(fragment).splitlines() if l.strip()]
    return "<br>".join(f"`{l.strip()}`" for l in lines)


def rows_of(section: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r'<tr class="(?:term|port)">(.*?)</tr>', section, re.S):
        r = m.group(1)
        n = re.search(r'<td class="num">(\d+)</td>', r).group(1)
        where = re.search(r'<span class="where">(.*?)</span>', r, re.S)
        doing = []
        if where:
            doing.append(f"**{strip(where.group(1))}**")
        # In card order: a click and the command it goes with are a sequence,
        # and reversing them turns "click here, then run this" into nonsense.
        act = r.split('class="act"', 1)[1].split("</td>", 1)[0]
        for c in re.finditer(r'<code class="cmd">(.*?)</code>'
                             r'|<span class="click">(.*?)</span>', act, re.S):
            cmd, click = c.group(1), c.group(2)
            doing.append(cell_command(cmd) if cmd is not None
                         else strip(click).replace("|", "\\|"))
        say = r.split('class="say"', 1)[1].split(">", 1)[1]
        out.append((n, "<br>".join(doing), text(say)))
    return out


def table(rows, head) -> str:
    lines = [f"| {head[0]} | {head[1]} | {head[2]} |", "|---|---|---|"]
    lines += [f"| {n} | {a} | {s} |" for n, a, s in rows]
    return "\n".join(lines)


def render(slug: str) -> str:
    src = (HERE / f"{slug}.html").read_text()
    title, seo, desc, nxt = PAGES[slug]
    body = src.split("</style>", 1)[1]

    screens = re.findall(r'<span class="what">(.*?)</span>\s*<span class="detail">(.*?)</span>',
                         body, re.S)
    setup = body.split("Pre-demo setup", 1)[1].split("The run-through", 1)[0]
    run = body.split("The run-through", 1)[1]

    front = [f"templateKey: doc", f'title: "Demo: {title}"', f'seoTitle: "{seo}"',
             f"description: {desc}", "next:"]
    for t, to in nxt:
        front.append(f"  - title: {t}\n    to: {to}")

    md = ["---", "\n".join(front), "---", ""]
    if len(screens) >= 2:
        md += [f"**Left screen** — {strip(screens[0][0])}, `{strip(screens[0][1])}`  ",
               f"**Right screen** — {strip(screens[1][0])}, `{strip(screens[1][1])}`", ""]
    md += ["## Pre-demo setup", "", table(rows_of(setup), ("#", "Run this", "What it does")), ""]
    md += ["## The run-through", "", table(rows_of(run), ("#", "Do this", "Say this")), ""]
    return "\n".join(md)


def main() -> None:
    for slug in PAGES:
        out = OUT / f"{SLUG[slug]}.md"
        out.write_text(render(slug))
        print(f"  wrote {out.name}")


if __name__ == "__main__":
    main()

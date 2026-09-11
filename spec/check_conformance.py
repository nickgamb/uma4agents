"""Every normative statement in the drafts, and what proves it.

Reads the rendered .txt of each draft in site/static/spec, finds every
sentence carrying MUST, MUST NOT, SHALL or SHALL NOT, and requires a row for
it in conformance.yaml. A row names one of:

  check:      a make target and the assertion text that target prints —
              the requirement is on this implementation and this proves it
  deployment: the requirement is on a deployment, not on this implementation
  binding:    the requirement is on a binding document, verified there

Every make target a row names has to exist in Makefile or Makefile.k8s, and
every row's quoted text has to still be in the draft. A specification that
asserts a behaviour should name the check that proves it; this is that
discipline, made to fail the build.
"""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
RENDERED = ROOT / "site/static/spec"
REGISTER = ROOT / "spec/conformance.yaml"
KEYWORDS = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL)\b")


def cleaned(txt: str) -> str:
    """The body of a rendered draft with page furniture removed."""
    body = txt.split("\n1.  Introduction", 1)[1]           # past the TOC
    body = body.split("\nAuthors' Addresses", 1)[0]
    # A page break lands wherever it lands, including inside a paragraph;
    # the footer, the header and the blank lines around them become one
    # newline so a sentence split across pages is read as one sentence.
    body = re.sub(r"[\n\f]+\S[^\n]*\[Page \d+\][\n\f]+(?:Internet-Draft[^\n]*[\n\f]+)?", "\n", body)
    return body


def sentences(txt: str):
    """Normative sentences from a rendered draft."""
    body = cleaned(txt)
    out = []
    for para in re.split(r"\n\s*\n", body):
        flat = " ".join(para.split())
        if not flat or re.match(r"^\d+(\.\d+)*\.\s", flat):  # a heading
            continue
        for sent in re.split(r"(?<=[.;:])\s+(?=[A-Z`\"(\-])", flat):
            if sent.startswith('The key words "MUST"'):      # BCP 14 boilerplate
                continue
            if KEYWORDS.search(sent):
                out.append(sent.strip())
    return out


def normalise(s: str) -> str:
    return " ".join(s.split()).lower()


def assertion_text():
    """Everything the suites print, so a register row cannot cite an assertion
    that nothing makes."""
    globs = ["lib/test_*.py", "clients/demo-driver/*.py", "clients/agent-shim/*.py",
             "clients/owner-cli/*.py", "k8s/base/jobs/*.yaml", "k8s/scripts/*",
             "Makefile", "Makefile.k8s", "integrations/*.py", "integrations/*/*.py",
             "kwaai/*.py", "clients/ts-agent/src/*.ts"]
    parts = []
    for g in globs:
        for f in ROOT.glob(g):
            if f.is_file():
                parts.append(f.read_text(errors="replace"))
    return normalise("\n".join(parts))


def make_targets():
    names = set()
    for mk in ("Makefile", "Makefile.k8s"):
        for line in (ROOT / mk).read_text().splitlines():
            m = re.match(r"^([a-z0-9][a-z0-9_-]*):", line)
            if m:
                names.add(m.group(1))
    return names


def main() -> int:
    register = yaml.safe_load(REGISTER.read_text())
    targets = make_targets()
    printed = assertion_text()
    problems = []
    total = covered = 0
    for draft, rows in register.items():
        path = RENDERED / f"{draft}.txt"
        if not path.exists():
            problems.append(f"{draft}: not rendered — run make spec"); continue
        txt = path.read_text()
        flat = normalise(cleaned(txt))
        found = sentences(txt)
        total += len(found)
        quoted = []
        for i, row in enumerate(rows, 1):
            q = row.get("text", "")
            if normalise(q) not in flat:
                problems.append(f"{draft} row {i}: quoted text not in draft: {q[:70]!r}")
            quoted.append(normalise(q))
            kind = row.get("verified")
            if kind == "check":
                for t in row.get("targets", []):
                    if t not in targets:
                        problems.append(f"{draft} row {i}: no make target {t!r}")
                if not row.get("targets") or not row.get("asserts"):
                    problems.append(f"{draft} row {i}: a check needs targets and asserts")
                for a in row.get("asserts", []):
                    if normalise(a) not in printed:
                        problems.append(f"{draft} row {i}: nothing prints {a!r}")
            elif kind in ("deployment", "binding"):
                if not row.get("because"):
                    problems.append(f"{draft} row {i}: {kind} needs a because")
            else:
                problems.append(f"{draft} row {i}: verified must be check|deployment|binding")
        for sent in found:
            n = normalise(sent)
            if any(q and (q in n or n in q) for q in quoted):
                covered += 1
            else:
                problems.append(f"{draft}: no register row for: {sent[:110]!r}")
    print(f"{covered} of {total} normative statements have a register row")
    for p in problems:
        print("  FAIL " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

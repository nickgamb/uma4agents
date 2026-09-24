"""Every normative statement in the drafts, and what proves it.

Reads the rendered .txt of each draft in site/static/spec, finds every
sentence carrying MUST, MUST NOT, SHALL or SHALL NOT, and requires a row for
it in conformance.yaml. A row names one of:

  check:      a make target and the assertion text that target prints —
              the requirement is on this implementation and this proves it
  deployment: the requirement is on a deployment, not on this implementation
  binding:    the requirement is on a binding document, verified there

Every make target a row names has to exist in Makefile or Makefile.k8s, and
every row's quoted text has to still be in the draft, and every assertion a
row quotes has to be printed by one of the targets that row names. A specification that
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


def _recipes() -> dict[str, tuple[list[str], str]]:
    """Each make target's prerequisites and recipe text."""
    out: dict[str, tuple[list[str], str]] = {}
    for mk in ("Makefile", "Makefile.k8s"):
        current = None
        for line in (ROOT / mk).read_text().splitlines():
            m = re.match(r"^([a-z0-9][a-z0-9_-]*):(?!=)(.*)$", line)
            if m and "?=" not in m.group(2):
                current = m.group(1)
                pre, text = out.get(current, ([], ""))
                out[current] = (pre + m.group(2).split(), text)
            elif line.startswith("\t") and current:
                pre, text = out[current]
                out[current] = (pre, text + line + "\n")
            elif line and not line.startswith("\t"):
                current = None
    return out


def _by_basename() -> dict[str, pathlib.Path]:
    """Scripts a container runs under another path, found by their name."""
    found = {}
    for g in ("clients/**/*.py", "clients/**/*.ts", "kwaai/**/*.py",
              "integrations/**/*.py", "lib/*.py"):
        for f in ROOT.glob(g):
            if "node_modules" not in f.parts:
                found.setdefault(f.name, f)
    return found


def target_text() -> dict[str, str]:
    """What each make target runs, as the text of the files it runs.

    A row names targets and quotes what they print, so the quote has to be in
    something those targets run — not merely somewhere in the repository.
    Followed from the recipe: files it names, compose services it runs, job
    manifests it applies, the scripts those mount, and its prerequisites.
    """
    recipes, named = _recipes(), _by_basename()
    compose: dict[str, list] = {}
    for f in ("docker-compose.yml", "compose.fixture.yml"):
        for name, svc in (yaml.safe_load((ROOT / f).read_text())["services"]).items():
            compose.setdefault(name, []).append(svc)
    path_re = re.compile(r"((?:lib|clients|kwaai|integrations|k8s|spec|mcp)/[\w./-]+\.(?:py|ts|yaml|sh))")
    dir_re = re.compile(r"\./((?:lib|clients|kwaai|integrations)(?:/[\w.-]+)*)/?:")
    inner_re = re.compile(r"/(?:driver|opt/u4a|app|work)/(?:[\w-]+/)*([\w-]+\.(?:py|ts))")

    def files_of(text: str) -> set[pathlib.Path]:
        text = text.replace("$(K8S)", "k8s")
        out = {ROOT / m for m in path_re.findall(text) if (ROOT / m).is_file()}
        out |= {named[m] for m in inner_re.findall(text) if m in named}
        # A mounted directory is where a service's own code lives (an agent's
        # sources, an ability), never what makes a suite run: the shared
        # library and the driver directory are mounted everywhere, and a test
        # module is not run by being mounted.
        for d in dir_re.findall(text):
            if d in ("lib", "clients/demo-driver"):
                continue
            out |= {f for g in ("*.py", "src/*.ts") for f in (ROOT / d).glob(g)
                    if not f.name.startswith("test_")}
        for command in re.findall(r"docker compose\b[^\n;&|]*", text):
            for word in command.split():
                for svc in compose.get(word, []):
                    out |= files_of(yaml.safe_dump(svc))
        return out

    cache: dict[str, str] = {}

    def text_of(target: str, seen: frozenset = frozenset()) -> str:
        if target in cache:
            return cache[target]
        pre, recipe = recipes.get(target, ([], ""))
        files = files_of(recipe)
        for f in list(files):                     # what a manifest mounts
            if f.suffix == ".yaml":
                files |= files_of(f.read_text(errors="replace"))
        parts = [recipe] + [f.read_text(errors="replace") for f in sorted(files)]
        parts += [text_of(t, seen | {target}) for t in pre
                  if t in recipes and t not in seen]
        cache[target] = normalise("\n".join(parts))
        return cache[target]

    return {t: text_of(t) for t in recipes}


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
    printed = target_text()
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
                named = " ".join(printed.get(t, "") for t in row.get("targets", []))
                for a in row.get("asserts", []):
                    if normalise(a) not in named:
                        problems.append(f"{draft} row {i}: none of "
                                        f"{row.get('targets')} prints {a!r}")
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

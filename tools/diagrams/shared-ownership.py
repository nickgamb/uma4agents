"""Shared ownership, as an animated diagram.

Same visual language as the reference-architecture slide: near-black ground,
lime for the thing your eye should land on, teal for structure, and VS Code
colours in the payload panels. Every string in a panel is a shape that is
actually on the wire.
"""
import os, re, subprocess, sys

W, H = 1280, 720
SCALE = 2

BG        = "#0a0b0d"
PANEL     = "#141619"
PANEL_2   = "#1a1d21"
STROKE    = "#2a2e35"
TEXT      = "#e8eaee"
DIM       = "#8b929c"
FAINT     = "#5d646d"
LIME      = "#bcdb2c"
TEAL      = "#8cc2d4"
TEAL_DEEP = "#5e8fa3"
WARN      = "#f2b955"
NEG       = "#ff5a6a"
POS       = "#2ed079"

ED_BG     = "#1e1e1e"
ED_CHROME = "#252526"
ED_TEXT   = "#d4d4d4"
ED_LINE   = "#858585"
ED_STR    = "#ce9178"
ED_KEY    = "#9cdcfe"
ED_NUM    = "#b5cea8"
ED_KW     = "#569cd6"
ED_COM    = "#6a9955"

SANS = "Inter, DejaVu Sans, sans-serif"
MONO = "DejaVu Sans Mono, Menlo, monospace"


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=14, fill=TEXT, weight="400", family=SANS, anchor="start",
         spacing="0"):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" '
            f'letter-spacing="{spacing}">{esc(s)}</text>')


def rect(x, y, w, h, fill=PANEL, stroke=STROKE, rx=10, sw=1, dash=None,
         opacity=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d} '
            f'opacity="{opacity}"/>')


def card(x, y, w, h, title, sub=None, tag=None, accent=TEAL_DEEP, glow=False,
         body=None):
    """A party or a resource. `glow` is what the beat is about."""
    out = []
    if glow:
        out.append(rect(x - 5, y - 5, w + 10, h + 10, "none", accent, rx=14,
                        sw=2, opacity=0.55))
    out.append(rect(x, y, w, h, PANEL, accent if glow else STROKE, rx=12,
                    sw=2 if glow else 1))
    out.append(f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{accent}"/>')
    ty = y + 26
    if tag:
        out.append(text(x + 18, ty, tag.upper(), 10, FAINT, "600", spacing="1.4"))
        ty += 20
    out.append(text(x + 18, ty, title, 16, TEXT, "600"))
    if sub:
        out.append(text(x + 18, ty + 20, sub, 12.5, DIM))
    if body:
        yy = ty + (42 if sub else 24)
        for line, colour in body:
            out.append(text(x + 18, yy, line, 12.5, colour, family=MONO))
            yy += 19
    return "".join(out)


def arrow(x1, y1, x2, y2, colour=TEAL_DEEP, width=2, dash=None, marker=True,
          opacity=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = ' marker-end="url(#head)"' if marker else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
            f'stroke-width="{width}"{d}{m} opacity="{opacity}" '
            f'stroke-linecap="round"/>')


def chip(x, y, label, colour=TEAL, fill=None, size=11.5):
    w = len(label) * size * 0.60 + 22
    f = fill or "#1b2026"
    return (rect(x, y, w, 24, f, colour, rx=12, sw=1, opacity=0.9)
            + text(x + 11, y + 16, label, size, colour, "600")), w


def tokens(line):
    """Colour a JSON-ish or Rego-ish line. Small on purpose: an approximate
    highlighter that is obviously approximate beats a clever one that is
    subtly wrong in a picture people will read closely."""
    if line.strip().startswith("#") or line.strip().startswith("//"):
        return [(line, ED_COM)]
    out, i = [], 0
    for m in re.finditer(r'"[^"]*"', line):
        if m.start() > i:
            out += _plain(line[i:m.start()])
        after = line[m.end():m.end() + 1]
        out.append((m.group(0), ED_KEY if after == ":" else ED_STR))
        i = m.end()
    if i < len(line):
        out += _plain(line[i:])
    return out


def _plain(s):
    out = []
    for part in re.split(r'(\b(?:true|false|null|if|contains|package|import|not|some|in)\b|\b\d+\b)', s):
        if not part:
            continue
        if re.fullmatch(r'\d+', part):
            out.append((part, ED_NUM))
        elif part in ("true", "false", "null", "if", "contains", "package",
                      "import", "not", "some", "in"):
            out.append((part, ED_KW))
        else:
            out.append((part, ED_TEXT))
    return out


def editor(x, y, w, lines, filename, note=None, size=12.6, lh=19):
    """A Monaco-style panel. Line numbers, a chrome bar, and the payload."""
    head = 30
    h = head + 14 + len(lines) * lh + 10
    out = [rect(x, y, w, h, ED_BG, "#2d2d2d", rx=8),
           f'<path d="M{x} {y+8} q0 -8 8 -8 h{w-16} q8 0 8 8 v{head-8} h-{w} z" fill="{ED_CHROME}"/>',
           f'<circle cx="{x+16}" cy="{y+15}" r="4" fill="{POS}"/>',
           text(x + 30, y + 19, filename, 11.5, "#cccccc", family=MONO)]
    if note:
        out.append(text(x + w - 14, y + 19, note, 11, FAINT, anchor="end"))
    ty = y + head + 20
    for n, line in enumerate(lines, 1):
        out.append(text(x + 30, ty, str(n).rjust(2), size, ED_LINE, anchor="end",
                        family=MONO))
        tx = x + 40
        parts = "".join(
            f'<tspan fill="{c}">{esc(t)}</tspan>' for t, c in tokens(line))
        out.append(f'<text x="{tx}" y="{ty}" font-family="{MONO}" '
                   f'font-size="{size}" xml:space="preserve">{parts}</text>')
        ty += lh
    return "".join(out), h


def frame(beat, title, kicker, stage, panels=""):
    defs = (f'<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{TEAL_DEEP}"/></marker>'
            f'<marker id="headLime" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{LIME}"/></marker>'
            f'<marker id="headNeg" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{NEG}"/></marker></defs>')
    hdr = (text(56, 58, "Shared ownership", 26, TEXT, "700", spacing="-0.3")
           + text(56, 84, kicker, 14, DIM)
           + text(W - 56, 58, f"{beat} / 7", 13, FAINT, anchor="end", family=MONO)
           + text(W - 56, 84, "u4a.ai", 12.5, LIME, anchor="end", weight="600")
           + f'<line x1="56" y1="102" x2="{W-56}" y2="102" stroke="{STROKE}" stroke-width="1"/>'
           + text(56, 128, title, 17, LIME, "600"))
    foot = (f'<line x1="56" y1="672" x2="{W-56}" y2="672" stroke="{STROKE}" '
            f'stroke-width="1"/>'
            + text(56, 696, "Every string above is a shape that is on the wire.",
                   12.5, FAINT)
            + text(W - 56, 696,
                   "make org-check  ·  80 assertions across six processes",
                   12.5, FAINT, anchor="end", family=MONO))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{defs}'
            f'<rect width="{W}" height="{H}" fill="{BG}"/>'
            f'{hdr}{stage}{panels}{foot}</svg>')


# ---------------------------------------------------------------- the stage
#
# Fixed positions across every beat, so the animation reads as one system with
# parts lighting up rather than seven unrelated pictures.

AX, AY, AW, AH = 56, 156, 300, 100          # Alice's authority
CX, CY = 56, 268                            # Carol's authority
BX, BY, BH = 56, 380, 92                    # the requesting side
RX, RY, RW = 430, 156, 330                  # Meridian's resource server
NX, NY, NW, NH = 830, 156, 394, 100         # Northwind
PY_ = 512                                   # every payload panel starts here


def resource_server(rows, note=None):
    """Meridian: one resource server, three owners of record behind it.

    The third row carries a second line rather than a second arrow. Two
    relationships reach it — Northwind owns it, a member administers access
    to it — and drawing both as curves put a crossing right where the eye
    lands.
    """
    h = 46 + len(rows) * 44 + (26 if note else 0)
    out = [rect(RX, RY, RW, h, "#101215", STROKE, rx=12),
           text(RX + 18, RY + 26, "MERIDIAN WEALTH", 10, FAINT, "600", spacing="1.4"),
           text(RX + 18, RY + 44, "one resource server", 12.5, DIM)]
    y = RY + 62
    for rid, owner, colour, glow in rows:
        out.append(rect(RX + 14, y, RW - 28, 34, PANEL_2 if not glow else "#1b2026",
                        colour if glow else STROKE, rx=8, sw=2 if glow else 1))
        out.append(text(RX + 26, y + 22, rid, 12.5, TEXT if glow else DIM, family=MONO))
        out.append(text(RX + RW - 26, y + 22, owner, 11, colour, anchor="end",
                        weight="600"))
        y += 44
    if note:
        out.append(text(RX + 26, y + 12, note, 11.5, LIME, "600"))
    return "".join(out)


def stage(*, alice_glow=False, org_glow=False, agent=None, book_owner=TEAL_DEEP,
          book_glow=False, shared_line=False, alice_body=None, org_body=None,
          agent_body=None, agent_colour=TEAL_DEEP, agent_title="Bob's agent",
          agent_sub="somebody else runs it"):
    out = []
    out.append(card(AX, AY, AW, AH, "Alice's authority", "her terms, her record",
                    "resource owner", TEAL, alice_glow, alice_body))
    out.append(card(CX, CY, AW, 96, "Carol's authority", "hers, separately",
                    "resource owner", TEAL_DEEP, False))
    out.append(card(BX, BY, AW, BH, agent_title, agent_sub, "requesting party",
                    agent_colour, agent == "glow", agent_body))
    out.append(resource_server([
        ("alice-vault/*", "Alice", TEAL, alice_glow),
        ("carol-vault/*", "Carol", TEAL_DEEP, False),
        ("northwind-vault/*", "Northwind", book_owner, book_glow),
    ], "administered by Alice at /mcp/shared/alice" if shared_line else None))
    out.append(card(NX, NY, NW, NH, "Northwind Capital", "owns the book · sets the charter",
                    "organization", LIME, org_glow, org_body))
    # Who governs what. Two different relationships reach the third row and
    # the picture has to keep them apart: Northwind *owns* the book, and a
    # member *administers* access to it.
    out.append(arrow(AX + AW, AY + 50, RX - 8, RY + 79, TEAL, 2))
    out.append(arrow(CX + AW, CY + 48, RX - 8, RY + 123, TEAL_DEEP, 1.6,
                     opacity=0.6))
    out.append(arrow(NX, NY + 50, RX + RW + 8, RY + 167, LIME, 2,
                     opacity=0.95 if org_glow else 0.55))
    out.append(text(RX + RW + 22, RY + 152, "owns", 11, LIME, "600"))
    return "".join(out)


FRAMES = []


def add(svg, ms):
    FRAMES.append((svg, ms))


# 1 ------------------------------------------------------------------------
add(frame(1, "A company can be an owner too",
          "U4A asks: can your agent access my stuff. This is what happens when some of that stuff is not mine.",
          stage(agent_title="Any agent", agent_sub="hers, or somebody else's",
                agent_colour=FAINT)), 3400)

# 2 ------------------------------------------------------------------------
panel, _ = editor(680, PY_, 544, [
    '"analyst": {',
    '  "grants": ["northwind-vault/get_positions",',
    '             "northwind-vault/get_transactions"],',
    '  "delegation": "first-party-only"',
    '}',
], "charter.roles", "what she joined for")
panel2, _ = editor(56, PY_, 588, [
    '# She is shown the whole charter, what it shares with her,',
    '# what it could never touch — and agrees, explicitly.',
    'POST /owner/organization  {"code": "…", "agreed": true}',
], "her side", "refused without it")
add(frame(2, "Joining is an exchange, not a submission",
          "The organization gets policy over its own resources. She gets access to them, under a role.",
          stage(org_glow=True, book_glow=True, book_owner=LIME,
                shared_line=True, agent_colour=FAINT, agent_title="Any agent",
                agent_sub="hers, or somebody else's",
                alice_body=[("alice-vault/*", DIM),
                            ("northwind-vault/*  shared", LIME)]),
          panel + panel2), 4200)

# 3 ------------------------------------------------------------------------
panel, _ = editor(56, PY_, 1168, [
    '"purpose":     "Desk research on the firm book",',
    '"expires_in":  3600,        # she wrote 86400. The charter caps it at 3600.',
    '"prohibited":  ["client-benchmarking",           # hers',
    '                "model-training", "retention-after-engagement"],   # the charter\'s',
    '"organization": {"name": "Northwind Capital", "charter_version": 4}',
], "alice/firmbook/v3 — the terms an agent dereferences and signs",
    "the ceiling is IN the document, not applied at the door")
add(frame(3, "Her terms. The charter's ceiling. In one document.",
          "A ceiling applied at grant time would leave a terms document that lies to the agent signing it.",
          stage(alice_glow=True, book_glow=True, book_owner=LIME,
                shared_line=True, agent_colour=FAINT, agent_title="Any agent",
                agent_sub="hers, or somebody else's",
                alice_body=[("northwind-vault/*  →  her tier", LIME)]),
          panel), 4200)

# 4 — Bob's agent asks, and travels ----------------------------------------
def travelling(t, colour=TEAL_DEEP):
    """A request moving from the agent to the resource server."""
    x = BX + AW + (RX - 8 - (BX + AW)) * t
    y = BY + 46 + (RY + 178 - (BY + 46)) * t
    return (arrow(BX + AW, BY + 46, RX - 8, RY + 178, colour, 2, dash="6 6",
                  marker=False, opacity=0.5)
            + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{colour}" opacity="0.95"/>'
            + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" fill="{colour}" opacity="0.18"/>')


challenge, _ = editor(56, PY_, 570, [
    'WWW-Authenticate: UMA realm="alice-vault",',
    '  as_uri="https://alice-as.uma.lab",      # hers, not the firm\'s',
    '  ticket="…", scope="positions:read"',
], "beat 1 — the challenge", "at /mcp/shared/alice")
for i in range(6):
    add(frame(4, "Bob's agent asks for the firm's book",
              "The challenge names HER authority — the book is Northwind's, the terms are hers.",
              stage(agent="glow", book_glow=True, book_owner=LIME,
                    shared_line=True, agent_colour=TEAL,
                    alice_body=[("northwind-vault/*  →  her tier", LIME)])
              + travelling(i / 5, TEAL), challenge), 130)

panel, _ = editor(56, PY_, 570, [
    'WWW-Authenticate: UMA realm="alice-vault",',
    '  as_uri="https://alice-as.uma.lab",      # hers, not the firm\'s',
    '  ticket="…", scope="positions:read"',
], "beat 1 — the challenge", "at /mcp/shared/alice")
panel2, _ = editor(660, PY_, 564, [
    '{"effect": "refuse", "governed": true, "because": [',
    '  "this member\'s role only lets agents she",',
    '  "operates herself act on the organization\'s",',
    '  "resources"]}',
], "the organization's decision — OPA", "delegation: first-party-only")
add(frame(4, "Refused — and not by her policy",
          "Her terms would have granted it. Both layers must allow, and either may refuse.",
          stage(agent="glow", book_glow=True, book_owner=NEG,
                shared_line=True, agent_colour=NEG,
                agent_sub="somebody else runs it → refused",
                alice_body=[("northwind-vault/*  →  her tier", LIME)])
          + f'<line x1="{BX+AW}" y1="{BY+46}" x2="{RX-8}" y2="{RY+178}" '
            f'stroke="{NEG}" stroke-width="2.4" stroke-dasharray="7 6" '
            f'marker-end="url(#headNeg)"/>',
          panel + panel2), 4400)

# 5 — her own agent --------------------------------------------------------
hers_panel, _ = editor(56, PY_, 1168, [
    '"standing": {"first_party": true}   # she claimed the operator, and her authority',
    '                                    # found this agent\'s key in its directory.',
    '# Not something the requesting side can assert. That is why a rule may rest on it.',
], "what her authority established", "the only difference between this beat and the last one")
for i in range(6):
    add(frame(5, "Her own agent asks. Same terms. Same key strength.",
              "The only thing that differs is whose agent it is — which is a fact about parties, not permissions.",
              stage(agent="glow", book_glow=True, book_owner=LIME,
                    shared_line=True, agent_colour=LIME,
                    agent_title="Alice's own agent",
                    agent_sub="she claimed the operator; it published the key",
                    alice_body=[("northwind-vault/*  →  her tier", LIME)])
              + travelling(i / 5, LIME), hers_panel), 130)

panel, _ = editor(56, PY_, 1168, [
    '"permissions": [{"resource_id": "northwind-vault/get_positions",',
    '                 "resource_scopes": ["positions:read"], "exp": 3600}],',
    '"cnf": {"jwk": {…}},        # bound to the key that asked',
    '"contract": "sha-256:…"     # the terms she wrote, counter-signed',
], "the grant", "and the firm's book comes back: NWCF · NWEQ · TLT · VNQ")
add(frame(5, "Granted — by her terms, inside their ceiling",
          "standing.first_party is her decision plus a check her authority ran. The requesting side cannot assert it.",
          stage(agent="glow", book_glow=True, book_owner=POS,
                shared_line=True, agent_colour=LIME,
                agent_title="Alice's own agent",
                agent_sub="granted",
                alice_body=[("northwind-vault/*  →  her tier", LIME)])
          + f'<line x1="{BX+AW}" y1="{BY+46}" x2="{RX-8}" y2="{RY+178}" '
            f'stroke="{LIME}" stroke-width="2.6" marker-end="url(#headLime)"/>',
          panel), 4400)

# 6 — where the organization's reach stops ---------------------------------
def two_columns():
    out = []
    cw = 556
    for x, title, colour, rows in (
        (56, "The organization CAN", WARN, [
            "see the agents that touch its book",
            "shut one out of its book — without ending",
            "  her relationship with it",
            "answer requests about its own resources",
            "refuse what her terms would have allowed",
            "reach its own book under a break-glass clause",
            "  she was shown — never quietly",
        ]),
        (668, "The organization CANNOT", POS, [
            "see the agents that touch her own accounts",
            "answer, or deny, a request about them",
            "read her policy — only that its ceiling",
            "  was applied, and which field bit",
            "widen anything she wrote",
            "act as her: every act is in her record",
            "  under his name, live on her screen",
        ]),
    ):
        out.append(rect(x, 156, cw, 316, PANEL, colour, rx=12, sw=1.5))
        out.append(text(x + 22, 192, title, 15, colour, "700", spacing="0.6"))
        y = 228
        for r in rows:
            lead = r.startswith("  ")
            out.append(text(x + (36 if lead else 22), y, ("" if lead else "· ") + r.strip(),
                            13.5, DIM if lead else TEXT))
            y += 30
    return "".join(out)


panel, _ = editor(56, PY_, 1168, [
    'GET /org/admin/alice/connections   →  agents granted at a tier that governs',
    '                                      northwind-vault/* — and no others',
    'POST .../connections/{h}/revoke    →  out of the firm\'s book. Her own access: untouched.',
], "her authority scopes before it answers", "the boundary is hers to enforce, not his to respect")
add(frame(6, "The reach stops at its own resources — including what it can see",
          "An organization that could enumerate every agent connected to her would have replaced her layer, not sat above it.",
          two_columns(), panel), 5200)

# 7 — leaving ---------------------------------------------------------------
panel, _ = editor(56, PY_, 1168, [
    'DELETE /owner/organization',
    '# the firm\'s book stops being hers to administer, and leaves her authority',
    '# her terms KEEP every narrowing the charter required',
    '#   leaving withdraws a ceiling. It does not raise what is underneath one.',
], "leaving", "anything she wants back, she widens herself")
add(frame(7, "Leaving takes back what joining gave — and nothing else",
          "Membership granted the access, so ending it ends the access. The narrowing stays.",
          stage(book_owner=FAINT, alice_glow=True, agent_colour=FAINT,
                agent_title="Any agent", agent_sub="nothing to ask for here now",
                alice_body=[("alice-vault/*", DIM),
                            ("northwind-vault/*  withdrawn", FAINT)]),
          panel), 4600)


# ---------------------------------------------------------------- rendering
out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(out_dir, exist_ok=True)
import cairosvg
from PIL import Image

pngs = []
for i, (svg, ms) in enumerate(FRAMES):
    p = os.path.join(out_dir, f"f{i:03d}.png")
    cairosvg.svg2png(bytestring=svg.encode(), write_to=p,
                     output_width=W * SCALE, output_height=H * SCALE)
    pngs.append((p, ms))

imgs = []
for p, _ in pngs:
    im = Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)
    imgs.append(im.quantize(colors=200, method=Image.MEDIANCUT, dither=Image.NONE))

gif = os.path.join(out_dir, "shared-ownership.gif")
imgs[0].save(gif, save_all=True, append_images=imgs[1:],
             duration=[ms for _, ms in pngs], loop=0, optimize=True, disposal=2)
print("wrote", gif, os.path.getsize(gif) // 1024, "KB", len(imgs), "frames")

# A still, for the docs.
with open(os.path.join(out_dir, "still.svg"), "w") as f:
    f.write(FRAMES[len(FRAMES) - 2][0] if len(FRAMES) > 1 else FRAMES[0][0])

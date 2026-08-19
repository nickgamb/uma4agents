import React from "react";
import DocFigure from "./DocFigure";
import DocSandbox from "./DocSandbox";
import DocInspector from "./DocInspector";
import { scriptFor } from "../data/figure-scripts";

/**
 * The documentation's diagrams, still and moving.
 *
 * Inline SVG rather than files under static/, for one reason: colour. Every
 * other surface on this site takes its colour from src/style/theme.js through
 * CSS custom properties, and an <img src="…svg"> is a separate document that
 * cannot see them. Inline, `var(--accent)` resolves against the page, so a
 * retheme moves the diagrams with everything else and none of these files
 * carries a hex value.
 *
 * A page names one of these in its frontmatter (`diagram: four-beats`). One per
 * page at most, and only where the picture shows a mechanism the prose cannot —
 * a diagram restating the paragraph above it is decoration with a download
 * cost.
 *
 * Some of them move. Motion is for the two things a still picture genuinely
 * cannot carry: *ordering* (what happens if you do these in a different
 * sequence) and *interleaving* (two things happening at once). The trust
 * boundary and the discovery split are structure, so they stay still.
 *
 * Drawn at a viewBox width of 600 with 15–19px type, so the labels survive
 * being scaled into a phone-width column. Anything that needs more room than
 * that needs to be two diagrams.
 */

/** One dim level for every figure that fades context back. */
const DIM = 0.14;

const MONO = "var(--mono)";
const UI = "var(--ui)";

const Frame = ({ title, viewBox, children }) => (
  <svg
    className="doc-diagram__svg"
    viewBox={viewBox}
    role="img"
    aria-label={title}
    fontFamily={UI}
  >
    <title>{title}</title>
    {children}
  </svg>
);

const Box = ({ x, y, w, h, stroke = "var(--edge)", fill = "var(--card)", ...rest }) => (
  <rect x={x} y={y} width={w} height={h} rx="8" fill={fill} stroke={stroke} {...rest} />
);

const Markers = () => (
  <defs>
    {[
      ["accent", "var(--accent)"],
      ["green", "var(--green)"],
      ["red", "var(--red)"],
      ["amber", "var(--amber)"],
    ].map(([id, fill]) => (
      <marker
        key={id}
        id={`arrow-${id}`}
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerWidth="6"
        markerHeight="6"
        orient="auto-start-reverse"
      >
        <path d="M0,0 L10,5 L0,10 z" fill={fill} />
      </marker>
    ))}
  </defs>
);

const markerFor = (colour) =>
  ({
    "var(--green)": "url(#arrow-green)",
    "var(--red)": "url(#arrow-red)",
    "var(--amber)": "url(#arrow-amber)",
  }[colour] || "url(#arrow-accent)");

const Arrow = ({ from, to, y, colour = "var(--accent)", dash }) => (
  <line
    x1={from}
    y1={y}
    x2={to}
    y2={y}
    stroke={colour}
    strokeWidth="1.6"
    strokeDasharray={dash}
    markerEnd={markerFor(colour)}
  />
);


/**
 * Zip a figure's captions in from src/data/figure-scripts.js.
 *
 * The scenes below describe motion only. Their words live in that file so the
 * Markdown twins, the search index and the MCP payload can read them too — a
 * caption that exists only in JSX is content agents cannot see. Counts must
 * agree, and a mismatch throws at build time rather than rendering a figure
 * with a blank caption.
 */
const scripted = (name, scenes) => {
  const steps = scriptFor(name);
  if (steps.length !== scenes.length) {
    throw new Error(
      `figure "${name}": ${scenes.length} scenes but ${steps.length} captions in src/data/figure-scripts.js`
    );
  }
  return scenes.map((scene, i) => ({ ...scene, text: steps[i] }));
};

// ---------------------------------------------------------------------------
// The four beats
// ---------------------------------------------------------------------------

const LANES = [
  { x: 78, label: "Bob's agent" },
  { x: 300, label: "Enforcement point" },
  { x: 522, label: "Alice's authority" },
];

const STEPS = [
  { y: 112, from: 0, to: 1, text: "call execute_trade", beat: "1" },
  { y: 146, from: 1, to: 2, text: "register the attempt", dash: "3 3" },
  { y: 180, from: 1, to: 0, text: "401 · ticket · as_uri", colour: "var(--red)" },
  { y: 236, from: 0, to: 2, text: "present the ticket", beat: "2" },
  { y: 270, from: 2, to: 0, text: "need_info · her terms", colour: "var(--amber)" },
  { y: 326, from: 0, to: 2, text: "signed agreement", beat: "3" },
  {
    y: 396,
    from: 2,
    to: 0,
    text: "grant · bound to this order",
    colour: "var(--green)",
    beat: "4",
  },
  { y: 440, from: 0, to: 1, text: "retry, signed", colour: "var(--green)" },
];

const FourBeats = () => (
  <Frame title="The four beats of a grant" viewBox="0 0 600 480">
    <Markers />

    {LANES.map((l) => (
      <g key={l.label}>
        <text x={l.x} y="26" textAnchor="middle" fill="var(--ink)" fontSize="14" fontWeight="600">
          {l.label}
        </text>
        <line x1={l.x} y1="40" x2={l.x} y2="460" stroke="var(--edge)" strokeWidth="1" />
      </g>
    ))}

    {/* Beat 3 is where she is asked, and the only beat that can wait. */}
    <g className="fb-wait">
      <rect
        x="470"
        y="344"
        width="104"
        height="34"
        rx="6"
        fill="var(--tint-granted)"
        stroke="var(--amber)"
      />
      <text x="522" y="365" textAnchor="middle" fill="var(--amber)" fontSize="12.5">
        Alice decides
      </text>
    </g>

    {STEPS.map((s, i) => {
      const x1 = LANES[s.from].x;
      const x2 = LANES[s.to].x;
      const forward = x2 > x1;
      return (
        <g key={i} className={`fb-step fb-step-${i}`}>
          {s.beat && (
            <text
              x="12"
              y={s.y + 4}
              fill="var(--primary)"
              fontSize="15"
              fontWeight="700"
              fontFamily={MONO}
            >
              {s.beat}
            </text>
          )}
          <Arrow
            from={forward ? x1 + 4 : x1 - 4}
            to={forward ? x2 - 6 : x2 + 6}
            y={s.y}
            colour={s.colour}
            dash={s.dash}
          />
          <text
            x={(x1 + x2) / 2}
            y={s.y - 8}
            textAnchor="middle"
            fill="var(--ink-2)"
            fontSize="12.5"
          >
            {s.text}
          </text>
        </g>
      );
    })}
  </Frame>
);

/** Which arrows belong to which beat. */
const BEAT_STEPS = [[0], [1, 2], [3, 4], [5], [6, 7]];

const dimAll = { ".fb-step": { opacity: DIM }, ".fb-wait": { opacity: DIM } };
const litThrough = (n) => {
  const state = { ...dimAll };
  BEAT_STEPS.slice(0, n + 1)
    .flat()
    .forEach((i) => {
      state[`.fb-step-${i}`] = { opacity: 1 };
    });
  return state;
};

const fourBeatScenes = scripted("four-beats", [
  {
    reset: dimAll,
    end: litThrough(0),
    play: (animate, $$) => animate($$(".fb-step-0"), { opacity: [DIM, 1], duration: 500 }),
  },
  {
    end: litThrough(1),
    play: (animate, $$) =>
      animate($$(".fb-step-1, .fb-step-2"), {
        opacity: [DIM, 1],
        duration: 500,
        delay: (el, i) => i * 320,
      }),
  },
  {
    end: litThrough(2),
    play: (animate, $$) =>
      animate($$(".fb-step-3, .fb-step-4"), {
        opacity: [DIM, 1],
        duration: 500,
        delay: (el, i) => i * 320,
      }),
  },
  {
    hold: 3600,
    end: { ...litThrough(3), ".fb-wait": { opacity: 1 } },
    play: (animate, $$) => {
      animate($$(".fb-step-5"), { opacity: [DIM, 1], duration: 500 });
      animate($$(".fb-wait"), {
        opacity: [DIM, 1],
        duration: 700,
        delay: 500,
      });
      animate($$(".fb-wait rect"), {
        strokeWidth: [1, 2.4, 1],
        duration: 1200,
        loop: 2,
        delay: 900,
      });
    },
  },
  {
    end: { ...litThrough(4), ".fb-wait": { opacity: 1 } },
    play: (animate, $$) =>
      animate($$(".fb-step-6, .fb-step-7"), {
        opacity: [DIM, 1],
        duration: 500,
        delay: (el, i) => i * 380,
      }),
  },
]);

// ---------------------------------------------------------------------------
// The trust boundary — structure, so it does not move
// ---------------------------------------------------------------------------

const TrustBoundary = () => (
  <Frame
    title="The trust boundary between the owner and the resource server"
    viewBox="0 0 600 330"
  >
    <Markers />

    <line
      className="tb-seam"
      x1="300"
      y1="14"
      x2="300"
      y2="316"
      stroke="var(--edge-strong)"
      strokeWidth="1.4"
      strokeDasharray="6 5"
    />

    <text x="24" y="28" fill="var(--accent)" fontSize="12" fontFamily={MONO} letterSpacing="1.4">
      ALICE — THE OWNER
    </text>
    <Box x={24} y={44} w={244} h={106} stroke="var(--accent)" />
    <text x="40" y="70" fill="var(--ink)" fontSize="14" fontWeight="600">
      Her authorization server
    </text>
    {["her policy and tiers", "her terms roster", "her connections and ledger"].map((t, i) => (
      <text key={t} x="40" y={92 + i * 19} fill="var(--ink-2)" fontSize="12.5">
        · {t}
      </text>
    ))}
    <Box x={24} y={166} w={244} h={52} stroke="var(--accent)" />
    <text x="40" y={197} fill="var(--ink)" fontSize="13.5">
      Her portal — where she is asked
    </text>

    <text x="332" y="28" fill="var(--ink-3)" fontSize="12" fontFamily={MONO} letterSpacing="1.4">
      MERIDIAN — THE RESOURCE SERVER
    </text>
    <Box x={332} y={44} w={244} h={70} />
    <text x="348" y="70" fill="var(--ink)" fontSize="14" fontWeight="600">
      Enforcement point
    </text>
    <text x="348" y="92" fill="var(--ink-2)" fontSize="12.5">
      refuses, verifies, spends
    </text>
    <Box x={332} y={130} w={244} h={62} />
    <text x="348" y="156" fill="var(--ink)" fontSize="14" fontWeight="600">
      The vault
    </text>
    <text x="348" y="177" fill="var(--ink-2)" fontSize="12.5">
      holds the assets
    </text>

    <g className="tb-allowed">
      <Arrow from={330} to={272} y={244} colour="var(--green)" />
      <text x="332" y={239} fill="var(--green)" fontSize="12.5">
        ticket · introspect · consume
      </text>
    </g>

    <g className="tb-refused">
      <line
        x1="330"
        y1="282"
        x2="272"
        y2="282"
        stroke="var(--red)"
        strokeWidth="1.6"
        strokeDasharray="4 4"
      />
      <g stroke="var(--red)" strokeWidth="2">
        <line x1="294" y1="276" x2="306" y2="288" />
        <line x1="306" y1="276" x2="294" y2="288" />
      </g>
      <text x="332" y={277} fill="var(--red)" fontSize="12.5">
        read her policy
      </text>
      <text x="332" y={296} fill="var(--ink-3)" fontSize="11.5">
        403 — same port, same workload
      </text>
    </g>
  </Frame>
);

const trustBoundaryScenes = scripted("trust-boundary", [
  {
    reset: { ".tb-allowed": { opacity: 0 }, ".tb-refused": { opacity: 0 } },
    end: {},
    // The seam is the subject of this scene, so it draws itself in.
    play: (animate, $$) =>
      animate($$(".tb-seam"), { opacity: [0, 1], strokeWidth: [3, 1.4], duration: 700 }),
  },
  {
    end: { ".tb-allowed": { opacity: 1 } },
    play: (animate, $$) => animate($$(".tb-allowed"), { opacity: [0, 1], duration: 600 }),
  },
  {
    hold: 4400,
    end: { ".tb-allowed": { opacity: 1 }, ".tb-refused": { opacity: 1 } },
    play: (animate, $$) => animate($$(".tb-refused"), { opacity: [0, 1], duration: 600 }),
  },
]);

// ---------------------------------------------------------------------------
// Discovery — structure, so it does not move
// ---------------------------------------------------------------------------

const DiscoveryLayers = () => (
  <Frame title="Public and protected discovery" viewBox="0 0 600 300">
    <Markers />

    <g className="dl-public">
      <Box x={20} y={30} w={560} h={104} />
      <text x="40" y="56" fill="var(--ink)" fontSize="14" fontWeight="600">
        Public — structure
      </text>
      <text x="560" y="56" textAnchor="end" fill="var(--green)" fontSize="12.5">
        anyone may ask
      </text>
      {[
        "which tools exist, and the scopes they need",
        "which authorization servers are authoritative",
        "the resource's keys, and metadata signed under them",
      ].map((t, i) => (
        <text key={t} x="40" y={80 + i * 19} fill="var(--ink-2)" fontSize="12.5">
          · {t}
        </text>
      ))}
    </g>

    <g className="dl-protected">
      <Box x={20} y={158} w={560} h={104} stroke="var(--accent)" />
      <text x="40" y="184" fill="var(--ink)" fontSize="14" fontWeight="600">
        Protected — instances
      </text>
      <text x="560" y="184" textAnchor="end" fill="var(--accent)" fontSize="12.5">
        only the owner's authority
      </text>
      {[
        "whose vault sits behind this resource",
        "the ids, names and scopes of her instances",
        "served only to an RFC 9421-signed query",
      ].map((t, i) => (
        <text key={t} x="40" y={208 + i * 19} fill="var(--ink-2)" fontSize="12.5">
          · {t}
        </text>
      ))}
    </g>

    <text className="dl-note" x="20" y="288" fill="var(--ink-3)" fontSize="11.5">
      Publishing the lower band openly would say which resources Alice owns to anyone who asks.
    </text>
  </Frame>
);

const discoveryScenes = scripted("discovery-layers", [
  {
    reset: { ".dl-protected": { opacity: DIM }, ".dl-note": { opacity: 0 } },
    end: {},
    play: (animate, $$) => animate($$(".dl-public"), { opacity: [DIM, 1], duration: 600 }),
  },
  {
    end: { ".dl-protected": { opacity: 1 } },
    play: (animate, $$) => animate($$(".dl-protected"), { opacity: [DIM, 1], duration: 600 }),
  },
  {
    hold: 4200,
    end: { ".dl-protected": { opacity: 1 }, ".dl-note": { opacity: 1 } },
    play: (animate, $$) => animate($$(".dl-note"), { opacity: [0, 1], duration: 600 }),
  },
]);

// ---------------------------------------------------------------------------
// The enforcement order
// ---------------------------------------------------------------------------

const EO_STEPS = [
  ["1", "Introspect", "live? connection standing?"],
  ["2", "Scope", "does this grant cover this tool?"],
  ["3", "Signature", "does the caller hold the key?"],
  ["4", "Operation", "is this the approved order?"],
  ["5", "Consume", "spend it — atomically"],
];

const EnforcementOrder = () => (
  <Frame title="The order enforcement runs in" viewBox="0 0 600 320">
    <Markers />
    {EO_STEPS.map(([n, name, note], i) => {
      const y = 20 + i * 56;
      const last = i === EO_STEPS.length - 1;
      return (
        <g key={n} className={`eo-step eo-step-${i}`}>
          <Box
            className="eo-box"
            x={20}
            y={y}
            w={420}
            h={44}
            stroke={last ? "var(--primary)" : "var(--edge)"}
            fill={last ? "var(--tint-granted)" : "var(--card)"}
          />
          <text
            x={40}
            y={y + 28}
            fill={last ? "var(--primary)" : "var(--ink-3)"}
            fontSize="15"
            fontWeight="700"
            fontFamily={MONO}
          >
            {n}
          </text>
          <text x={64} y={y + 28} fill="var(--ink)" fontSize="14" fontWeight="600">
            {name}
          </text>
          <text x={168} y={y + 28} fill="var(--ink-2)" fontSize="12.5">
            {note}
          </text>
          {i < EO_STEPS.length - 1 && (
            <line
              x1="30"
              y1={y + 44}
              x2="30"
              y2={y + 56}
              stroke="var(--edge-strong)"
              strokeWidth="1.4"
            />
          )}
        </g>
      );
    })}

    <g className="eo-wrong">
      <line
        x1="452"
        y1="42"
        x2="452"
        y2="278"
        stroke="var(--edge)"
        strokeWidth="1"
        strokeDasharray="4 4"
      />
      <text x="466" y="34" fill="var(--red)" fontSize="12.5" fontWeight="600">
        Spending here
      </text>
      <text x="466" y="52" fill="var(--ink-2)" fontSize="12">
        instead lets an
      </text>
      <text x="466" y="68" fill="var(--ink-2)" fontSize="12">
        unsigned replay
      </text>
      <text x="466" y="84" fill="var(--ink-2)" fontSize="12">
        destroy an approval
      </text>
      <text x="466" y="100" fill="var(--ink-2)" fontSize="12">
        Alice just gave.
      </text>
      <g stroke="var(--red)" strokeWidth="1.8">
        <line x1="446" y1="14" x2="458" y2="26" />
        <line x1="458" y1="14" x2="446" y2="26" />
      </g>
    </g>
  </Frame>
);

const eoDim = { ".eo-step": { opacity: DIM }, ".eo-wrong": { opacity: 0 } };
const eoLit = (n) => {
  const state = { ...eoDim };
  for (let i = 0; i <= n; i += 1) state[`.eo-step-${i}`] = { opacity: 1 };
  return state;
};

const enforcementScenes = scripted("enforcement-order", [
  ...EO_STEPS.map((_step, i) => ({
    reset: eoDim,
    end: eoLit(i),
    play: (animate, $$) => animate($$(`.eo-step-${i}`), { opacity: [DIM, 1], duration: 420 }),
  })),
  {
    hold: 4200,
    end: { ...eoLit(4), ".eo-wrong": { opacity: 1 } },
    play: (animate, $$) => {
      animate($$(".eo-wrong"), { opacity: [0, 1], duration: 600 });
      animate($$(".eo-step-4 .eo-box"), {
        stroke: ["var(--primary)", "var(--red)", "var(--primary)"],
        duration: 1400,
        loop: 2,
        delay: 400,
      });
    },
  },
]);

// ---------------------------------------------------------------------------
// The single-use race
// ---------------------------------------------------------------------------

const SingleUseRace = () => (
  <Frame title="Two replicas spending one single-use grant" viewBox="0 0 600 268">
    <Markers />

    <text x="20" y="24" fill="var(--ink-3)" fontSize="11.5" fontFamily={MONO} letterSpacing="1.2">
      ONE APPROVED TRADE · TWO COPIES OF THE CALL
    </text>

    {/* The two replicas */}
    {[0, 1].map((i) => (
      <g key={i} className={`su-replica su-replica-${i}`}>
        <Box x={20} y={44 + i * 62} w={168} h={48} />
        <text x={36} y={72 + i * 62} fill="var(--ink)" fontSize="13.5" fontWeight="600">
          Replica {String.fromCharCode(65 + i)}
        </text>
        <text x={36} y={88 + i * 62} fill="var(--ink-2)" fontSize="11.5" fontFamily={MONO}>
          jti rpt_8f3a
        </text>
      </g>
    ))}

    {/* The store */}
    <Box className="su-store" x={396} y={44} w={184} h={110} stroke="var(--accent)" />
    <text x={412} y={70} fill="var(--ink)" fontSize="13.5" fontWeight="600">
      The store
    </text>
    <text x={412} y={94} fill="var(--ink-2)" fontSize="12" fontFamily={MONO}>
      consumed =
    </text>
    <text
      className="su-flag"
      x={504}
      y={94}
      fill="var(--red)"
      fontSize="12"
      fontWeight="700"
      fontFamily={MONO}
    >
      false
    </text>
    {/* Under the box rather than inside it: the atomic form is a statement,
        and a statement does not fit in a 184-wide panel at a readable size. */}
    <text className="su-mode" x={396} y={172} fill="var(--ink-3)" fontSize="11.5" fontFamily={MONO}>
      read → decide → write
    </text>
    <text
      className="su-mode-atomic"
      x={396}
      y={172}
      fill="var(--primary)"
      fontSize="11.5"
      fontFamily={MONO}
      opacity="0"
    >
      UPDATE … WHERE NOT consumed
    </text>

    {/* Reads */}
    <g className="su-read-0">
      <Arrow from={192} to={392} y={68} colour="var(--amber)" />
      <text x={292} y={60} textAnchor="middle" fill="var(--amber)" fontSize="11.5">
        read → false
      </text>
    </g>
    <g className="su-read-1">
      <Arrow from={192} to={392} y={130} colour="var(--amber)" />
      <text x={292} y={122} textAnchor="middle" fill="var(--amber)" fontSize="11.5">
        read → false
      </text>
    </g>

    {/* Outcomes, as a verdict on each replica rather than a return arrow.
        Arrows back along the same lanes as the reads put four labels within
        twenty pixels of each other and none of them stayed readable. */}
    <g className="su-out-0">
      <text x={172} y={72} textAnchor="end" fill="var(--red)" fontSize="12" fontWeight="700">
        allowed
      </text>
    </g>
    <g className="su-out-1">
      <text x={172} y={134} textAnchor="end" fill="var(--red)" fontSize="12" fontWeight="700">
        allowed
      </text>
    </g>

    <g className="su-verdict-bad">
      <rect x={20} y={182} width={560} height={40} rx="8" fill="var(--card)" stroke="var(--red)" />
      <text x={300} y={207} textAnchor="middle" fill="var(--red)" fontSize="13">
        The trade executes twice, and nothing logs an error.
      </text>
    </g>

    {/* The atomic pass */}
    <g className="su-win">
      <Arrow from={392} to={196} y={68} colour="var(--green)" />
      <text x={292} y={60} textAnchor="middle" fill="var(--green)" fontSize="11.5">
        1 row
      </text>
      <text x={172} y={72} textAnchor="end" fill="var(--green)" fontSize="12" fontWeight="700">
        allowed
      </text>
    </g>
    <g className="su-lose">
      <Arrow from={392} to={196} y={130} colour="var(--red)" />
      <text x={292} y={122} textAnchor="middle" fill="var(--red)" fontSize="11.5">
        0 rows
      </text>
      <text x={172} y={134} textAnchor="end" fill="var(--red)" fontSize="12" fontWeight="700">
        denied
      </text>
    </g>

    <g className="su-verdict-good">
      <rect x={20} y={182} width={560} height={40} rx="8" fill="var(--card)" stroke="var(--primary)" />
      <text x={300} y={207} textAnchor="middle" fill="var(--primary)" fontSize="13">
        One caller wins. The decision and the record are the same operation.
      </text>
    </g>

    <text className="su-foot" x={20} y={252} fill="var(--ink-3)" fontSize="11.5">
      Nothing here is slower. The difference is where the decision is made.
    </text>
  </Frame>
);

const suHide = {
  ".su-read-0": { opacity: 0 },
  ".su-read-1": { opacity: 0 },
  ".su-out-0": { opacity: 0 },
  ".su-out-1": { opacity: 0 },
  ".su-win": { opacity: 0 },
  ".su-lose": { opacity: 0 },
  ".su-verdict-bad": { opacity: 0 },
  ".su-verdict-good": { opacity: 0 },
  ".su-mode-atomic": { opacity: 0 },
  ".su-mode": { opacity: 1 },
  ".su-foot": { opacity: 0 },
  ".su-flag": { opacity: 1 },
};

const singleUseScenes = scripted("single-use-race", [
  {
    reset: suHide,
    end: {},
    play: (animate, $$) =>
      animate($$(".su-replica"), {
        opacity: [DIM, 1],
        duration: 500,
        delay: (el, i) => i * 200,
      }),
  },
  {
    end: { ".su-read-0": { opacity: 1 }, ".su-read-1": { opacity: 1 } },
    play: (animate, $$) =>
      animate($$(".su-read-0, .su-read-1"), {
        opacity: [0, 1],
        duration: 500,
        delay: (el, i) => i * 260,
      }),
  },
  {
    hold: 4000,
    end: {
      ".su-read-0": { opacity: 1 },
      ".su-read-1": { opacity: 1 },
      ".su-out-0": { opacity: 1 },
      ".su-out-1": { opacity: 1 },
      ".su-verdict-bad": { opacity: 1 },
    },
    play: (animate, $$) => {
      animate($$(".su-out-0, .su-out-1"), {
        opacity: [0, 1],
        duration: 420,
        delay: (el, i) => i * 200,
      });
      animate($$(".su-verdict-bad"), { opacity: [0, 1], duration: 600, delay: 600 });
    },
  },
  {
    // The failed pass has to be cleared, not merely covered — its arrows and
    // its verdict occupy the same coordinates as the ones that replace them.
    end: {
      ".su-mode": { opacity: 0 },
      ".su-mode-atomic": { opacity: 1 },
      ".su-read-0": { opacity: 0 },
      ".su-read-1": { opacity: 0 },
      ".su-out-0": { opacity: 0 },
      ".su-out-1": { opacity: 0 },
      ".su-verdict-bad": { opacity: 0 },
    },
    play: (animate, $$) => {
      animate($$(".su-read-0, .su-read-1, .su-out-0, .su-out-1, .su-verdict-bad"), {
        opacity: [1, 0],
        duration: 400,
      });
      animate($$(".su-mode"), { opacity: [1, 0], duration: 300 });
      animate($$(".su-mode-atomic"), { opacity: [0, 1], duration: 500, delay: 300 });
      animate($$(".su-store"), { stroke: ["var(--accent)", "var(--primary)"], duration: 600 });
    },
  },
  {
    hold: 4000,
    end: {
      ".su-mode": { opacity: 0 },
      ".su-mode-atomic": { opacity: 1 },
      ".su-read-0": { opacity: 0 },
      ".su-read-1": { opacity: 0 },
      ".su-out-0": { opacity: 0 },
      ".su-out-1": { opacity: 0 },
      ".su-verdict-bad": { opacity: 0 },
      ".su-win": { opacity: 1 },
      ".su-lose": { opacity: 1 },
      ".su-verdict-good": { opacity: 1 },
      ".su-foot": { opacity: 1 },
    },
    play: (animate, $$) => {
      animate($$(".su-win, .su-lose"), {
        opacity: [0, 1],
        duration: 420,
        delay: (el, i) => i * 240,
      });
      animate($$(".su-verdict-good"), { opacity: [0, 1], duration: 600, delay: 600 });
      animate($$(".su-foot"), { opacity: [0, 1], duration: 600, delay: 900 });
    },
  },
]);

// ---------------------------------------------------------------------------
// Who can answer — the cast from the home page, asking one question
// ---------------------------------------------------------------------------

const FIG = {
  fill: "none",
  stroke: "var(--ink)",
  strokeWidth: 2.6,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

/** Alice and Bob are the same figure with different hair; the agent is a bot. */
const Person = ({ x, hair, tie, label, sub, className }) => (
  <g className={className} transform={`translate(${x} 210)`}>
    <circle cx="0" cy="-62" r="10" {...FIG} />
    <path d={hair} {...FIG} strokeWidth="2.2" />
    <path d="M0 -52 V-24" {...FIG} />
    {tie && <path d="M0 -50 l-3.5 3.5 l3.5 12 l3.5 -12 z" fill="var(--accent)" stroke="none" />}
    <path d="M0 -45 L-15 -33" {...FIG} />
    <path d="M0 -45 L15 -33" {...FIG} />
    <path d="M0 -24 L-11 0" {...FIG} />
    <path d="M0 -24 L11 0" {...FIG} />
    <text x="0" y="22" textAnchor="middle" fill="var(--ink)" fontSize="12.5" fontWeight="600">
      {label}
    </text>
    <text x="0" y="38" textAnchor="middle" fill="var(--ink-3)" fontSize="11">
      {sub}
    </text>
  </g>
);

const WhoAnswers = () => (
  // Cropped rather than redrawn: the cast stands on a ground line at y=210 and
  // nothing uses the top of the canvas, so the window starts below it.
  <Frame title="Who has standing to answer for Alice" viewBox="0 60 600 212">
    <Markers />
    <line x1="20" y1="210" x2="580" y2="210" stroke="var(--edge)" strokeWidth="2" />

    <Person
      className="wa-bob"
      x={90}
      hair="M-10 -67q10 -6 20 0"
      tie
      label="Bob"
      sub="the requesting party"
    />

    {/* Bob's agent. Not a villain — simply not Alice. */}
    <g className="wa-agent" transform="translate(212 210)">
      <path d="M0 -72 V-66" {...FIG} />
      <circle cx="0" cy="-74" r="3" fill="var(--agent)" />
      <rect x="-14" y="-66" width="28" height="22" rx="7" fill="var(--card-2)" stroke="var(--agent)" strokeWidth="2.2" />
      <circle cx="-5" cy="-55" r="2.6" fill="var(--accent)" />
      <circle cx="5" cy="-55" r="2.6" fill="var(--accent)" />
      <rect x="-11" y="-40" width="22" height="22" rx="6" fill="var(--card-2)" stroke="var(--agent)" strokeWidth="2.2" />
      <path d="M-11 -33 L-20 -26" {...FIG} />
      <path d="M11 -33 L20 -26" {...FIG} />
      <path d="M-5 -18 V0" {...FIG} />
      <path d="M5 -18 V0" {...FIG} />
      <text x="0" y="22" textAnchor="middle" fill="var(--ink)" fontSize="12.5" fontWeight="600">
        His agent
      </text>
      <text x="0" y="38" textAnchor="middle" fill="var(--ink-3)" fontSize="11">
        holds its own key
      </text>
    </g>

    {/* Meridian — many owners, one server. */}
    <g className="wa-vault" transform="translate(390 210)">
      <rect x="-56" y="-104" width="112" height="104" rx="9" fill="var(--card)" stroke="var(--edge)" strokeWidth="2" />
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          x="-44"
          y={-92 + i * 30}
          width="88"
          height="22"
          rx="4"
          fill="var(--card-2)"
          stroke="var(--edge)"
          strokeWidth="1.4"
          opacity={i === 1 ? 1 : 0.5}
        />
      ))}
      <rect x="-44" y="-62" width="88" height="22" rx="4" fill="var(--sunken)" stroke="var(--accent)" strokeWidth="1.6" />
      <text x="0" y="22" textAnchor="middle" fill="var(--ink)" fontSize="12.5" fontWeight="600">
        Meridian
      </text>
      <text x="0" y="38" textAnchor="middle" fill="var(--ink-3)" fontSize="11">
        many owners, one server
      </text>
    </g>

    {/* Alice's authority. */}
    <g className="wa-as" transform="translate(530 210)">
      <rect x="-44" y="-90" width="88" height="90" rx="9" fill="var(--card)" stroke="var(--accent)" strokeWidth="2" />
      <path d="M-44 -90 L0 -116 L44 -90 Z" fill="var(--card-2)" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      <path
        className="wa-shield"
        d="M0 -76 l18 7 v14 q0 16 -18 23 q-18 -7 -18 -23 v-14 z"
        fill="var(--sunken)"
        stroke="var(--accent)"
        strokeWidth="2.2"
      />
      <path className="wa-tick" d="M-7 -52 l5 6 l10 -11" fill="none" stroke="var(--green)" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" opacity="0" />
      <text x="0" y="22" textAnchor="middle" fill="var(--ink)" fontSize="12.5" fontWeight="600">
        Her authority
      </text>
      <text x="0" y="38" textAnchor="middle" fill="var(--ink-3)" fontSize="11">
        her policy, her side
      </text>
    </g>

    {/* The ask, and the two parties who cannot answer it. */}
    <g className="wa-ask">
      <Arrow from={238} to={328} y={150} colour="var(--agent)" />
      <text x={283} y={142} textAnchor="middle" fill="var(--ink-2)" fontSize="11.5">
        may I?
      </text>
    </g>

    <g className="wa-no-bob" opacity="0">
      <circle cx="90" cy="120" r="17" fill="var(--sunken)" stroke="var(--red)" strokeWidth="2" />
      <path d="M83 113 L97 127 M97 113 L83 127" stroke="var(--red)" strokeWidth="2.4" strokeLinecap="round" />
      <text x="90" y="96" textAnchor="middle" fill="var(--red)" fontSize="11">
        not his to give
      </text>
    </g>

    <g className="wa-no-vault" opacity="0">
      <circle cx="390" cy="128" r="17" fill="var(--sunken)" stroke="var(--red)" strokeWidth="2" />
      <path d="M383 121 L397 135 M397 121 L383 135" stroke="var(--red)" strokeWidth="2.4" strokeLinecap="round" />
      <text x="390" y="104" textAnchor="middle" fill="var(--red)" fontSize="11">
        holds it, cannot decide
      </text>
    </g>

    {/* The payoff line goes above the cast rather than beside the building,
        which is the only part of the canvas nothing else occupies. */}
    <g className="wa-yes" opacity="0">
      <Arrow from={452} to={486} y={150} colour="var(--green)" />
      <text
        x="300"
        y="82"
        textAnchor="middle"
        fill="var(--primary)"
        fontSize="15"
        fontWeight="650"
      >
        She isn’t online. Her policy is.
      </text>
    </g>
  </Frame>
);

const waHide = {
  ".wa-ask": { opacity: 0 },
  ".wa-no-bob": { opacity: 0 },
  ".wa-no-vault": { opacity: 0 },
  ".wa-yes": { opacity: 0 },
  ".wa-tick": { opacity: 0 },
};

const whoAnswersScenes = scripted("who-answers", [
  {
    reset: waHide,
    end: { ".wa-ask": { opacity: 1 } },
    play: (animate, $$) => {
      // Opacity only. These groups carry a `transform` attribute for their
      // position, and anime composes its own transform from x/y/scale — which
      // replaces the attribute and drops the actor at the origin.
      animate($$(".wa-agent"), { opacity: [DIM, 1], duration: 700, ease: "outQuad" });
      animate($$(".wa-ask"), { opacity: [0, 1], duration: 500, delay: 400 });
    },
  },
  {
    end: { ".wa-ask": { opacity: 1 }, ".wa-no-bob": { opacity: 1 } },
    play: (animate, $$) => animate($$(".wa-no-bob"), { opacity: [0, 1], duration: 500 }),
  },
  {
    end: { ".wa-ask": { opacity: 1 }, ".wa-no-bob": { opacity: 1 }, ".wa-no-vault": { opacity: 1 } },
    play: (animate, $$) => animate($$(".wa-no-vault"), { opacity: [0, 1], duration: 500 }),
  },
  {
    hold: 4600,
    end: {
      ".wa-ask": { opacity: 1 },
      ".wa-no-bob": { opacity: 1 },
      ".wa-no-vault": { opacity: 1 },
      ".wa-yes": { opacity: 1 },
      ".wa-tick": { opacity: 1 },
    },
    play: (animate, $$) => {
      animate($$(".wa-yes"), { opacity: [0, 1], duration: 600 });
      animate($$(".wa-tick"), { opacity: [0, 1], duration: 500, delay: 400 });
      animate($$(".wa-shield"), {
        stroke: ["var(--accent)", "var(--green)", "var(--accent)"],
        duration: 1400,
        loop: 2,
        delay: 400,
      });
    },
  },
]);

// ---------------------------------------------------------------------------
// Terms: proffered, signed, counter-signed, held by both
// ---------------------------------------------------------------------------

/** A sheet of terms. The one light surface in the set, as on the home page. */
const Sheet = ({ x, y, label, signedBy }) => (
  <g transform={`translate(${x} ${y})`}>
    <rect x="0" y="0" width="104" height="76" rx="6" fill="var(--paper)" />
    {[0, 1, 2].map((i) => (
      <line
        key={i}
        x1="14"
        y1={20 + i * 14}
        x2={i === 2 ? 68 : 90}
        y2={20 + i * 14}
        stroke="var(--paper-line)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    ))}
    {signedBy && (
      <path
        d="M16 66 q10 -12 20 0 t20 -2"
        fill="none"
        stroke={signedBy}
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    )}
    <text x="52" y="-8" textAnchor="middle" fill="var(--ink-2)" fontSize="11.5">
      {label}
    </text>
  </g>
);

const TermsExchange = () => (
  <Frame title="How terms are proffered, signed and kept" viewBox="0 0 600 240">
    <Markers />

    <text x="60" y="24" textAnchor="middle" fill="var(--accent)" fontSize="12" fontFamily={MONO}>
      ALICE
    </text>
    <text x="540" y="24" textAnchor="middle" fill="var(--agent)" fontSize="12" fontFamily={MONO}>
      THE AGENT
    </text>

    <g className="te-proffer">
      <Sheet x={8} y={64} label="her template" />
      <Arrow from={124} to={230} y={102} colour="var(--amber)" />
      <text x={177} y={94} textAnchor="middle" fill="var(--amber)" fontSize="11.5">
        need_info
      </text>
      {/* Two short lines rather than one long one: the gap between the sheets
          is 106 units wide and a single line ran underneath the next sheet. */}
      <text x={177} y={122} textAnchor="middle" fill="var(--ink-3)" fontSize="10.5">
        purpose · scope
      </text>
      <text x={177} y={136} textAnchor="middle" fill="var(--ink-3)" fontSize="10.5">
        expiry · prohibited
      </text>
    </g>

    <g className="te-sign">
      <Sheet x={244} y={64} label="echoed and signed" signedBy="var(--agent)" />
      <text x={296} y={158} textAnchor="middle" fill="var(--ink-3)" fontSize="11">
        the same key it will
      </text>
      <text x={296} y={174} textAnchor="middle" fill="var(--ink-3)" fontSize="11">
        prove possession with
      </text>
    </g>

    <g className="te-verify">
      <Arrow from={356} to={230} y={196} colour="var(--red)" />
      <text x={293} y={216} textAnchor="middle" fill="var(--red)" fontSize="11.5">
        weakened echo → refused
      </text>
    </g>

    <g className="te-receipt">
      <Sheet x={480} y={64} label="dual record" signedBy="var(--green)" />
      <Arrow from={366} to={472} y={102} colour="var(--green)" />
      <text x={419} y={94} textAnchor="middle" fill="var(--green)" fontSize="11.5">
        receipt
      </text>
      <text x={419} y={122} textAnchor="middle" fill="var(--ink-3)" fontSize="10.5">
        counter-signed,
      </text>
      <text x={419} y={136} textAnchor="middle" fill="var(--ink-3)" fontSize="10.5">
        embedding hers
      </text>
    </g>
  </Frame>
);

const termsScenes = scripted("terms-exchange", [
  {
    reset: {
      ".te-sign": { opacity: 0 },
      ".te-verify": { opacity: 0 },
      ".te-receipt": { opacity: 0 },
    },
    end: {},
    play: (animate, $$) => animate($$(".te-proffer"), { opacity: [DIM, 1], duration: 600 }),
  },
  {
    end: { ".te-sign": { opacity: 1 } },
    play: (animate, $$) => animate($$(".te-sign"), { opacity: [0, 1], duration: 600 }),
  },
  {
    hold: 4200,
    end: { ".te-sign": { opacity: 1 }, ".te-verify": { opacity: 1 } },
    play: (animate, $$) => animate($$(".te-verify"), { opacity: [0, 1], duration: 600 }),
  },
  {
    hold: 4600,
    end: {
      ".te-sign": { opacity: 1 },
      ".te-verify": { opacity: 1 },
      ".te-receipt": { opacity: 1 },
    },
    play: (animate, $$) => animate($$(".te-receipt"), { opacity: [0, 1], duration: 600 }),
  },
]);

// ---------------------------------------------------------------------------
// Proof-of-possession
// ---------------------------------------------------------------------------

const PopKey = () => (
  <Frame title="Why a stolen grant is not enough" viewBox="0 0 600 250">
    <Markers />

    {[
      ["pop-good", 44, "The agent that holds the key", "var(--green)", "allowed"],
      ["pop-thief", 118, "Anyone who copied the token", "var(--red)", "refused — no signature"],
      ["pop-tamper", 192, "The same agent, body changed", "var(--red)", "refused — digest"],
    ].map(([cls, y, who, colour, verdict]) => (
      <g key={cls} className={cls}>
        <Box x={20} y={y - 20} w={232} h={40} />
        <text x={36} y={y + 5} fill="var(--ink)" fontSize="12.5">
          {who}
        </text>
        <Arrow from={258} to={352} y={y} colour={colour} />
        <Box
          x={360}
          y={y - 20}
          w={220}
          h={40}
          stroke={colour}
          fill={colour === "var(--green)" ? "var(--tint-granted)" : "var(--card)"}
        />
        <text x={376} y={y + 5} fill={colour} fontSize="12.5" fontWeight="600">
          {verdict}
        </text>
      </g>
    ))}

    <text x="20" y="234" fill="var(--ink-3)" fontSize="11.5" fontFamily={MONO}>
      signature base: @method @authority @path authorization · digest over the body
    </text>
  </Frame>
);

const popScenes = scripted("proof-of-possession", [
  {
    reset: { ".pop-thief": { opacity: DIM }, ".pop-tamper": { opacity: DIM } },
    end: {},
    play: (animate, $$) => animate($$(".pop-good"), { opacity: [DIM, 1], duration: 500 }),
  },
  {
    end: { ".pop-thief": { opacity: 1 } },
    play: (animate, $$) => animate($$(".pop-thief"), { opacity: [DIM, 1], duration: 500 }),
  },
  {
    hold: 4200,
    end: { ".pop-thief": { opacity: 1 }, ".pop-tamper": { opacity: 1 } },
    play: (animate, $$) => animate($$(".pop-tamper"), { opacity: [DIM, 1], duration: 500 }),
  },
]);

// ---------------------------------------------------------------------------
// Identity is not authorization
// ---------------------------------------------------------------------------

const IdentityVsAuthz = () => (
  <Frame title="Knowing who is asking does not answer whether they may" viewBox="0 0 600 210">
    <Markers />

    <g className="iv-known">
      <Box x={20} y={40} w={250} h={110} stroke="var(--agent)" />
      <text x={36} y={66} fill="var(--ink)" fontSize="13.5" fontWeight="600">
        What identity establishes
      </text>
      {[
        "which agent this is, across sessions",
        "who operates it",
        "that it holds the key it claims",
      ].map((t, i) => (
        <text key={t} x={36} y={90 + i * 19} fill="var(--ink-2)" fontSize="12">
          ✓ {t}
        </text>
      ))}
    </g>

    <g className="iv-gap">
      <Arrow from={278} to={322} y={95} colour="var(--red)" />
      <text x={300} y={82} textAnchor="middle" fill="var(--red)" fontSize="11.5">
        still
      </text>
      <text x={300} y={122} textAnchor="middle" fill="var(--red)" fontSize="11.5">
        shut
      </text>
    </g>

    <g className="iv-unknown">
      <Box x={330} y={40} w={250} h={110} stroke="var(--edge)" />
      <text x={346} y={66} fill="var(--ink)" fontSize="13.5" fontWeight="600">
        What it does not
      </text>
      {[
        "whether the owner agreed",
        "on what terms, and for how long",
        "how she takes it back",
      ].map((t, i) => (
        <text key={t} x={346} y={90 + i * 19} fill="var(--ink-2)" fontSize="12">
          ? {t}
        </text>
      ))}
    </g>

    <g className="iv-answer">
      <rect x={20} y={166} width={560} height={34} rx="8" fill="var(--tint-granted)" stroke="var(--primary)" />
      <text x={300} y={188} textAnchor="middle" fill="var(--primary)" fontSize="13">
        Only the owner's authority answers the right-hand column.
      </text>
    </g>
  </Frame>
);

const identityScenes = scripted("identity-vs-authz", [
  {
    reset: { ".iv-gap": { opacity: 0 }, ".iv-unknown": { opacity: DIM }, ".iv-answer": { opacity: 0 } },
    end: {},
    play: (animate, $$) => animate($$(".iv-known"), { opacity: [DIM, 1], duration: 500 }),
  },
  {
    end: { ".iv-gap": { opacity: 1 }, ".iv-unknown": { opacity: 1 } },
    play: (animate, $$) => {
      animate($$(".iv-unknown"), { opacity: [DIM, 1], duration: 500 });
      animate($$(".iv-gap"), { opacity: [0, 1], duration: 500, delay: 300 });
    },
  },
  {
    hold: 4200,
    end: { ".iv-gap": { opacity: 1 }, ".iv-unknown": { opacity: 1 }, ".iv-answer": { opacity: 1 } },
    play: (animate, $$) => animate($$(".iv-answer"), { opacity: [0, 1], duration: 600 }),
  },
]);


// ---------------------------------------------------------------------------
// The two intents: her record, filling up
// ---------------------------------------------------------------------------

// The earlier version of this figure drew the *taxonomy* — four fields in,
// two enforced and two recorded out. It was accurate and it explained
// nothing, because the thing worth seeing about intent here happens over
// time. This draws her register filling up instead: the rows are what she
// can actually see, and the last one is the only interesting thing in it.

const REG_ROWS = [
  { tier: "tier1", what: "promised — “quarterly review for the client”" },
  { tier: "tier1", what: "touched — get_positions" },
  { tier: "tier1", what: "touched — get_positions" },
  { tier: "tier1", what: "touched — get_positions" },
  { tier: "tier2", what: "promised — transaction history", wide: true },
];

const Register = () => (
  <Frame title="One agent, as it appears in the owner's own record" viewBox="0 0 600 296">
    <Markers />

    <text x={24} y={40} fill="var(--accent)" fontSize="11" fontFamily={MONO}>
      HER TERMS
    </text>
    <g className="tr-terms">
      <Sheet x={24} y={56} label="" />
      <text x={24} y={158} fill="var(--ink-3)" fontSize="11">
        written first
      </text>
      <text x={24} y={174} fill="var(--ink-3)" fontSize="11">
        names no agent
      </text>
    </g>

    <path d="M158 34 V262" stroke="var(--edge)" strokeWidth="1"
          strokeDasharray="4 5" fill="none" />

    <text x={182} y={40} fill="var(--accent)" fontSize="11" fontFamily={MONO}>
      HER REGISTER
    </text>

    {REG_ROWS.map((row, i) => (
      <g className={row.wide ? "tr-wide" : `tr-r${i < 2 ? 0 : 1}`} key={i}>
        <Box
          x={182}
          y={52 + i * 32}
          w={394}
          h={26}
          stroke={row.wide ? "var(--amber)" : "var(--edge)"}
          fill="var(--sunken)"
        />
        <text
          x={194}
          y={70 + i * 32}
          fill={row.wide ? "var(--amber)" : "var(--accent)"}
          fontSize="10.5"
          fontFamily={MONO}
        >
          {row.tier}
        </text>
        <text x={248} y={70 + i * 32} fill="var(--ink-2)" fontSize="11.5">
          {row.what}
        </text>
      </g>
    ))}

    <g className="tr-ask">
      <text x={182} y={238} fill="var(--amber)" fontSize="11.5">
        one row at a tier it has never reached before
      </text>
      <text x={182} y={258} fill="var(--ink-3)" fontSize="11">
        nothing had to be reported to her for this to be visible
      </text>
    </g>
  </Frame>
);

const TR_TERMS = { ".tr-terms": { opacity: 1 } };
const TR_FIRST = { ...TR_TERMS, ".tr-r0": { opacity: 1 } };
const TR_MORE = { ...TR_FIRST, ".tr-r1": { opacity: 1 } };
const TR_ALL = { ...TR_MORE, ".tr-wide": { opacity: 1 }, ".tr-ask": { opacity: 1 } };

const registerScenes = scripted("two-intents", [
  {
    reset: {
      ".tr-terms": { opacity: DIM },
      ".tr-r0": { opacity: 0 },
      ".tr-r1": { opacity: 0 },
      ".tr-wide": { opacity: 0 },
      ".tr-ask": { opacity: 0 },
    },
    end: TR_TERMS,
    play: (animate, $$) => animate($$(".tr-terms"), { opacity: [DIM, 1], duration: 520 }),
  },
  {
    end: TR_FIRST,
    play: (animate, $$) =>
      animate($$(".tr-r0"), { opacity: [0, 1], duration: 420, delay: (_, i) => i * 160 }),
  },
  {
    end: TR_MORE,
    play: (animate, $$) =>
      animate($$(".tr-r1"), { opacity: [0, 1], duration: 420, delay: (_, i) => i * 160 }),
  },
  {
    hold: 4600,
    end: TR_ALL,
    play: (animate, $$) => {
      animate($$(".tr-wide"), { opacity: [0, 1], duration: 520 });
      animate($$(".tr-ask"), { opacity: [0, 1], duration: 620, delay: 220 });
    },
  },
]);

// ---------------------------------------------------------------------------
// Revocation
// ---------------------------------------------------------------------------

const RevokeCascade = () => (
  <Frame title="Revoking a connection and the grants behind it" viewBox="0 0 600 230">
    <Markers />

    <Box className="rv-conn" x={20} y={36} w={220} h={58} stroke="var(--accent)" />
    <text x={36} y={60} fill="var(--ink)" fontSize="13.5" fontWeight="600">
      Connection
    </text>
    <text className="rv-status" x={36} y={80} fill="var(--green)" fontSize="12" fontFamily={MONO}>
      active
    </text>
    <text className="rv-status-off" x={36} y={80} fill="var(--red)" fontSize="12" fontFamily={MONO} opacity="0">
      revoked
    </text>

    {[0, 1, 2].map((i) => (
      <g key={i} className={`rv-grant rv-grant-${i}`}>
        <Box x={330} y={30 + i * 46} w={250} h={36} stroke="var(--green)" fill="var(--tint-granted)" />
        <text x={346} y={53 + i * 46} fill="var(--ink)" fontSize="12" fontFamily={MONO}>
          rpt_{["8f3a", "b21c", "44de"][i]}
        </text>
        <text
          className="rv-live"
          x={566}
          y={53 + i * 46}
          textAnchor="end"
          fill="var(--green)"
          fontSize="11.5"
        >
          live
        </text>
      </g>
    ))}

    <g className="rv-burn">
      <Arrow from={248} to={322} y={100} colour="var(--red)" />
      <text x={285} y={90} textAnchor="middle" fill="var(--red)" fontSize="11.5">
        one
      </text>
      <text x={285} y={120} textAnchor="middle" fill="var(--red)" fontSize="11.5">
        statement
      </text>
    </g>

    <g className="rv-terminal">
      <rect x={20} y={172} width={560} height={40} rx="8" fill="var(--card)" stroke="var(--red)" />
      <text x={300} y={197} textAnchor="middle" fill="var(--red)" fontSize="12.5">
        Introspection answers connection_revoked — terminal, not an invitation to renegotiate.
      </text>
    </g>
  </Frame>
);

const revokeScenes = scripted("revoke-cascade", [
  {
    reset: { ".rv-burn": { opacity: 0 }, ".rv-terminal": { opacity: 0 }, ".rv-status-off": { opacity: 0 } },
    end: {},
    play: (animate, $$) =>
      animate($$(".rv-grant"), { opacity: [DIM, 1], duration: 450, delay: (el, i) => i * 160 }),
  },
  {
    hold: 4400,
    end: {
      ".rv-status": { opacity: 0 },
      ".rv-status-off": { opacity: 1 },
      ".rv-burn": { opacity: 1 },
      ".rv-grant .rv-live": { opacity: 0 },
      ".rv-grant rect": { stroke: "var(--red)" },
    },
    play: (animate, $$) => {
      animate($$(".rv-status"), { opacity: [1, 0], duration: 300 });
      animate($$(".rv-status-off"), { opacity: [0, 1], duration: 400, delay: 200 });
      animate($$(".rv-burn"), { opacity: [0, 1], duration: 400 });
      animate($$(".rv-grant rect"), {
        stroke: ["var(--green)", "var(--red)"],
        duration: 600,
        delay: (el, i) => 300 + i * 140,
      });
      animate($$(".rv-grant .rv-live"), { opacity: [1, 0], duration: 400, delay: 400 });
    },
  },
  {
    hold: 4400,
    end: {
      ".rv-status": { opacity: 0 },
      ".rv-status-off": { opacity: 1 },
      ".rv-burn": { opacity: 1 },
      ".rv-grant .rv-live": { opacity: 0 },
      ".rv-grant rect": { stroke: "var(--red)" },
      ".rv-terminal": { opacity: 1 },
    },
    play: (animate, $$) => animate($$(".rv-terminal"), { opacity: [0, 1], duration: 600 }),
  },
]);

// ---------------------------------------------------------------------------
// The six roles, and where each one sits
// ---------------------------------------------------------------------------

const ROLES = [
  {
    n: "1",
    key: "authority",
    x: 366,
    y: 34,
    w: 214,
    h: 50,
    name: "An authority on her side",
    short: "Her authority",
    must: "Holds her policy, dictates terms, mints grants, and answers while she is offline.",
    judge: "Judge it by who can change the rules, not by where it runs.",
  },
  {
    n: "2",
    key: "pep",
    x: 176,
    y: 34,
    w: 152,
    h: 50,
    name: "An enforcement point",
    short: "Enforcement point",
    must: "Refuses before forwarding, returns a ticket, verifies a signature, and spends a single-use grant.",
    judge: "Judge it by whether its callout can control the response body, not just the verdict.",
  },
  {
    n: "3",
    key: "resource",
    x: 176,
    y: 116,
    w: 152,
    h: 50,
    name: "A resource that says what it is",
    short: "The resource",
    must: "Publishes its tool surfaces, its scopes, and which authorization servers speak for it.",
    judge: "Usually the cheapest role to fill: the resource itself does not have to change.",
  },
  {
    n: "4",
    key: "store",
    x: 366,
    y: 100,
    w: 104,
    h: 50,
    name: "Somewhere to store single-use state",
    short: "The store",
    must: "Decides and records in one indivisible operation, and reports who won.",
    judge: "If you would write this as read-then-write, it is the wrong store.",
  },
  {
    n: "5",
    key: "reach",
    x: 476,
    y: 100,
    w: 104,
    h: 50,
    name: "A way to reach her",
    short: "Her surface",
    must: "Notifies her, shows what is asked and on what terms, takes a decision, releases the hold.",
    judge: "Judge it by latency tolerance — she may be asleep for hours.",
  },
  {
    n: "6",
    key: "identity",
    x: 20,
    y: 76,
    w: 122,
    h: 50,
    name: "An identity for the agent",
    short: "Agent identity",
    must: "Gives the agent a stable name her authority recognises across sessions.",
    judge: "Judge it by whether the name survives key rotation.",
  },
];

const RolesMap = () => (
  <Frame title="The six roles and where each one sits" viewBox="0 0 600 200">
    <Markers />

    <line x1="158" y1="8" x2="158" y2="192" stroke="var(--edge)" strokeWidth="1" strokeDasharray="5 5" />
    <line x1="348" y1="8" x2="348" y2="192" stroke="var(--edge-strong)" strokeWidth="1.4" strokeDasharray="6 5" />

    <text x="80" y="20" textAnchor="middle" fill="var(--agent)" fontSize="10.5" fontFamily={MONO} letterSpacing="1">
      REQUESTING SIDE
    </text>
    <text x="252" y="20" textAnchor="middle" fill="var(--ink-3)" fontSize="10.5" fontFamily={MONO} letterSpacing="1">
      RESOURCE SERVER
    </text>
    <text x="472" y="20" textAnchor="middle" fill="var(--accent)" fontSize="10.5" fontFamily={MONO} letterSpacing="1">
      THE OWNER
    </text>

    {/* The connections between them, drawn under the boxes. */}
    <g className="rm-wires">
      <Arrow from={146} to={170} y={100} colour="var(--agent)" />
      <Arrow from={252} to={252} y={90} colour="var(--ink-3)" />
      <line x1="252" y1="84" x2="252" y2="116" stroke="var(--ink-3)" strokeWidth="1.2" />
      <Arrow from={332} to={360} y={59} colour="var(--ink-3)" />
      <line x1="420" y1="84" x2="420" y2="100" stroke="var(--accent)" strokeWidth="1.2" />
      <line x1="528" y1="84" x2="528" y2="100" stroke="var(--accent)" strokeWidth="1.2" />
    </g>

    {ROLES.map((r) => (
      <g key={r.key} className={`rm-role rm-${r.key}`}>
        <Box
          className="rm-box"
          x={r.x}
          y={r.y}
          w={r.w}
          h={r.h}
          stroke={r.x >= 348 ? "var(--accent)" : r.x < 158 ? "var(--agent)" : "var(--edge)"}
        />
        <text
          x={r.x + 12}
          y={r.y + 20}
          fill="var(--primary)"
          fontSize="12"
          fontWeight="700"
          fontFamily={MONO}
        >
          {r.n}
        </text>
        <text x={r.x + 28} y={r.y + 20} fill="var(--ink)" fontSize="11.5" fontWeight="600">
          {r.short}
        </text>
        <text x={r.x + 12} y={r.y + 38} fill="var(--ink-2)" fontSize="10.5">
          {
            {
              authority: "policy · terms · grants",
              pep: "refuses · verifies · spends",
              resource: "publishes what it protects",
              store: "one statement",
              reach: "notify · decide",
              identity: "a name that persists",
            }[r.key]
          }
        </text>
      </g>
    ))}
  </Frame>
);

const rolesScenes = scripted(
  "roles-map",
  ROLES.map((r) => ({
    hold: 5200,
    reset: { ".rm-role": { opacity: DIM }, ".rm-wires": { opacity: DIM } },
    end: { [`.rm-${r.key}`]: { opacity: 1 } },
    play: (animate, $$) => animate($$(`.rm-${r.key}`), { opacity: [DIM, 1], duration: 450 }),
  }))
);

// ---------------------------------------------------------------------------
// One core, two hosts
// ---------------------------------------------------------------------------

const TwoHosts = () => (
  <Frame title="One enforcement core behind two hosts" viewBox="0 0 600 250">
    <Markers />

    <g className="th-gateway">
      <Box x={20} y={24} w={230} h={70} />
      <text x={36} y={48} fill="var(--ink)" fontSize="13" fontWeight="600">
        A gateway, as a callout
      </text>
      <text x={36} y={68} fill="var(--ink-2)" fontSize="11.5">
        ext-authz before forwarding
      </text>
      <text x={36} y={84} fill="var(--ink-3)" fontSize="11">
        HTTP request → facts
      </text>
    </g>

    <g className="th-embedded">
      <Box x={350} y={24} w={230} h={70} />
      <text x={366} y={48} fill="var(--ink)" fontSize="13" fontWeight="600">
        The resource, in-process
      </text>
      <text x={366} y={68} fill="var(--ink-2)" fontSize="11.5">
        middleware, no gateway at all
      </text>
      <text x={366} y={84} fill="var(--ink-3)" fontSize="11">
        framework request → facts
      </text>
    </g>

    <g className="th-core">
      <Box x={150} y={128} w={300} h={78} stroke="var(--primary)" fill="var(--tint-granted)" />
      <text x={300} y={154} textAnchor="middle" fill="var(--ink)" fontSize="13.5" fontWeight="600">
        One enforcement core
      </text>
      <text x={300} y={176} textAnchor="middle" fill="var(--ink-2)" fontSize="12" fontFamily={MONO}>
        AuthzFacts → Decision
      </text>
      <text x={300} y={195} textAnchor="middle" fill="var(--ink-3)" fontSize="11">
        refuse · challenge · verify · bind · spend
      </text>
    </g>

    <g className="th-wires">
      <line x1="135" y1="94" x2="200" y2="126" stroke="var(--accent)" strokeWidth="1.4" markerEnd="url(#arrow-accent)" />
      <line x1="465" y1="94" x2="400" y2="126" stroke="var(--accent)" strokeWidth="1.4" markerEnd="url(#arrow-accent)" />
    </g>

    <text className="th-note" x={300} y={232} textAnchor="middle" fill="var(--ink-3)" fontSize="11.5">
      Each host only converts its own request in, and its own response out.
    </text>
  </Frame>
);

const twoHostsScenes = scripted("two-hosts", [
  {
    reset: {
      ".th-embedded": { opacity: DIM },
      ".th-core": { opacity: DIM },
      ".th-wires": { opacity: 0 },
      ".th-note": { opacity: 0 },
    },
    end: {},
    play: (animate, $$) => animate($$(".th-gateway"), { opacity: [DIM, 1], duration: 500 }),
  },
  {
    end: { ".th-embedded": { opacity: 1 } },
    play: (animate, $$) => animate($$(".th-embedded"), { opacity: [DIM, 1], duration: 500 }),
  },
  {
    hold: 4400,
    end: {
      ".th-embedded": { opacity: 1 },
      ".th-core": { opacity: 1 },
      ".th-wires": { opacity: 1 },
      ".th-note": { opacity: 1 },
    },
    play: (animate, $$) => {
      animate($$(".th-core"), { opacity: [DIM, 1], duration: 500 });
      animate($$(".th-wires"), { opacity: [0, 1], duration: 500, delay: 300 });
      animate($$(".th-note"), { opacity: [0, 1], duration: 500, delay: 600 });
    },
  },
]);

// ---------------------------------------------------------------------------
// A challenge you must not trust
// ---------------------------------------------------------------------------

const RogueChallenge = () => (
  <Frame title="Corroborating a challenge against published metadata" viewBox="0 0 600 240">
    <Markers />

    <Box x={20} y={30} w={150} h={54} stroke="var(--agent)" />
    <text x={95} y={54} textAnchor="middle" fill="var(--ink)" fontSize="13" fontWeight="600">
      The agent
    </text>
    <text x={95} y={72} textAnchor="middle" fill="var(--ink-3)" fontSize="11">
      about to negotiate
    </text>

    <g className="rc-challenge">
      <Arrow from={280} to={180} y={57} colour="var(--red)" />
      <Box x={288} y={30} w={292} h={54} stroke="var(--red)" />
      <text x={304} y={50} fill="var(--red)" fontSize="12" fontWeight="600">
        401 · as_uri = attacker.example
      </text>
      <text x={304} y={70} fill="var(--ink-3)" fontSize="11">
        anything able to refuse can name an authority
      </text>
    </g>

    <g className="rc-metadata">
      <Box x={288} y={108} w={292} h={54} stroke="var(--accent)" />
      <text x={304} y={128} fill="var(--ink)" fontSize="12" fontWeight="600">
        The resource's published metadata
      </text>
      <text x={304} y={148} fill="var(--ink-2)" fontSize="11" fontFamily={MONO}>
        authorization_servers: [alice-as]
      </text>
      <Arrow from={180} to={280} y={135} colour="var(--accent)" />
    </g>

    <g className="rc-verdict">
      <rect x={20} y={186} width={560} height={38} rx="8" fill="var(--card)" stroke="var(--red)" />
      <text x={300} y={210} textAnchor="middle" fill="var(--red)" fontSize="12.5">
        Named authority is not one the resource published — refuse, and do not negotiate.
      </text>
    </g>
  </Frame>
);

const rogueScenes = scripted("rogue-challenge", [
  {
    reset: { ".rc-metadata": { opacity: 0 }, ".rc-verdict": { opacity: 0 } },
    end: {},
    play: (animate, $$) => animate($$(".rc-challenge"), { opacity: [DIM, 1], duration: 500 }),
  },
  {
    end: { ".rc-metadata": { opacity: 1 } },
    play: (animate, $$) => animate($$(".rc-metadata"), { opacity: [0, 1], duration: 500 }),
  },
  {
    hold: 4400,
    end: { ".rc-metadata": { opacity: 1 }, ".rc-verdict": { opacity: 1 } },
    play: (animate, $$) => animate($$(".rc-verdict"), { opacity: [0, 1], duration: 600 }),
  },
]);

// ---------------------------------------------------------------------------
// Which specification supplies which piece
// ---------------------------------------------------------------------------

const SPEC_GROUPS = [
  {
    key: "base",
    label: "The base",
    y: 30,
    specs: ["UMA 2.0 Grant", "FedAuthz", "OAuth 2.0", "OpenID Connect"],
    supplies: "the grant type, the ticket, the party split",
  },
  {
    key: "hold",
    label: "What makes it hold",
    y: 92,
    specs: ["RFC 9728", "RFC 9421", "RFC 7638", "RFC 9396"],
    supplies: "discovery, proof-of-possession, the agent's name, the ask",
  },
  {
    key: "person",
    label: "What makes it about a person",
    y: 154,
    specs: ["IEEE 7012"],
    supplies: "the owner proffers terms; the counterparty agrees",
  },
  {
    key: "agent",
    label: "Agent identity",
    y: 216,
    specs: ["AAuth", "Web Bot Auth", "CIMD"],
    supplies: "who is asking — consumed, never an authorization input",
  },
];

const StandardsMap = () => (
  <Frame title="Which specification supplies which piece" viewBox="0 0 600 274">
    <Markers />
    {SPEC_GROUPS.map((g) => (
      <g key={g.key} className={`sm-group sm-${g.key}`}>
        <Box
          x={20}
          y={g.y}
          w={560}
          h={50}
          stroke={g.key === "person" ? "var(--primary)" : "var(--edge)"}
          fill={g.key === "person" ? "var(--tint-granted)" : "var(--card)"}
        />
        <text x={36} y={g.y + 21} fill="var(--ink)" fontSize="12.5" fontWeight="600">
          {g.label}
        </text>
        <text x={36} y={g.y + 39} fill="var(--ink-2)" fontSize="11">
          {g.supplies}
        </text>
        <text
          x={564}
          y={g.y + 21}
          textAnchor="end"
          fill={g.key === "person" ? "var(--primary)" : "var(--accent)"}
          fontSize="10.5"
          fontFamily={MONO}
        >
          {g.specs.join(" · ")}
        </text>
      </g>
    ))}
  </Frame>
);

const standardsScenes = scripted(
  "standards-map",
  SPEC_GROUPS.map((g, i) => ({
    hold: 4200,
    reset: { ".sm-group": { opacity: DIM } },
    end: Object.fromEntries(
      SPEC_GROUPS.slice(0, i + 1).map((x) => [`.sm-${x.key}`, { opacity: 1 }])
    ),
    play: (animate, $$) => animate($$(`.sm-${g.key}`), { opacity: [DIM, 1], duration: 450 }),
  }))
);

// ---------------------------------------------------------------------------
// Keep, transform, add
// ---------------------------------------------------------------------------

const VERDICTS = [
  {
    key: "keep",
    label: "Carried unchanged",
    colour: "var(--green)",
    items: ["the cross-principal topology", "the permission ticket", "the pending state"],
  },
  {
    key: "transform",
    label: "Changed shape",
    colour: "var(--amber)",
    items: ["claims-gathering becomes proffered terms", "the RPT becomes proof-of-possession", "registration becomes pulled"],
  },
  {
    key: "add",
    label: "Genuinely new",
    colour: "var(--primary)",
    items: ["per-operation, single-use grants", "the owner's app as the consent surface"],
  },
];

const CompareUma = () => (
  <Frame title="What this profile keeps, changes and adds" viewBox="0 0 600 250">
    <Markers />
    {VERDICTS.map((v, i) => (
      <g key={v.key} className={`cu-col cu-${v.key}`}>
        <Box x={20 + i * 192} y={30} w={176} h={190} stroke={v.colour} />
        <text
          x={108 + i * 192}
          y={54}
          textAnchor="middle"
          fill={v.colour}
          fontSize="12"
          fontWeight="700"
        >
          {v.label}
        </text>
        {v.items.map((t, j) => (
          <text
            key={t}
            x={36 + i * 192}
            y={84 + j * 42}
            fill="var(--ink-2)"
            fontSize="11"
          >
            {t.length > 26 ? (
              <>
                <tspan x={36 + i * 192}>{t.slice(0, t.lastIndexOf(" ", 26))}</tspan>
                <tspan x={36 + i * 192} dy="14">
                  {t.slice(t.lastIndexOf(" ", 26) + 1)}
                </tspan>
              </>
            ) : (
              t
            )}
          </text>
        ))}
      </g>
    ))}
  </Frame>
);

const compareUmaScenes = scripted(
  "compare-uma",
  VERDICTS.map((v, i) => ({
    hold: 4400,
    reset: { ".cu-col": { opacity: DIM } },
    end: Object.fromEntries(
      VERDICTS.slice(0, i + 1).map((x) => [`.cu-${x.key}`, { opacity: 1 }])
    ),
    play: (animate, $$) => animate($$(`.cu-${v.key}`), { opacity: [DIM, 1], duration: 450 }),
  }))
);

// ---------------------------------------------------------------------------
// The ticket's states — structure, so it does not move
// ---------------------------------------------------------------------------

/** A state box. Terminal states carry their outcome's colour. */
const State = ({ x, y, w = 116, label, sub, tone = "var(--edge)" }) => (
  <g>
    <Box x={x} y={y} w={w} h={sub ? 44 : 32} stroke={tone} />
    <text
      x={x + w / 2}
      y={y + (sub ? 20 : 21)}
      textAnchor="middle"
      fill={tone === "var(--edge)" ? "var(--ink)" : tone}
      fontSize="11.5"
      fontWeight="600"
      fontFamily={MONO}
    >
      {label}
    </text>
    {sub && (
      <text x={x + w / 2} y={y + 36} textAnchor="middle" fill="var(--ink-3)" fontSize="10">
        {sub}
      </text>
    )}
  </g>
);

/** An edge with its label above it. */
const Edge = ({ x1, y1, x2, y2, label, tone = "var(--ink-3)", labelDy = -6 }) => (
  <g>
    <path
      d={y1 === y2 ? `M${x1} ${y1} H${x2}` : `M${x1} ${y1} V${(y1 + y2) / 2} H${x2} V${y2}`}
      fill="none"
      stroke={tone}
      strokeWidth="1.3"
      markerEnd={markerFor(tone)}
    />
    {label && (
      <text
        x={y1 === y2 ? (x1 + x2) / 2 : x2}
        y={y1 === y2 ? y1 + labelDy : (y1 + y2) / 2 + labelDy}
        textAnchor="middle"
        fill={tone === "var(--ink-3)" ? "var(--ink-2)" : tone}
        fontSize="10"
      >
        {label}
      </text>
    )}
  </g>
);

const TicketLifecycle = () => (
  <Frame title="The states a permission ticket moves through" viewBox="0 0 600 300">
    <Markers />

    <State x={16} y={40} label="issued" tone="var(--accent)" />
    <Edge x1={132} y1={56} x2={196} y2={56} label="present" />

    <State x={200} y={34} w={132} label="need_info" sub="rotated, terms offered" tone="var(--amber)" />
    <Edge x1={332} y1={56} x2={396} y2={56} label="commit" />

    {/* The three ways a committed agreement resolves. */}
    <State x={400} y={16} w={184} label="granted" sub="known agent, open tier" tone="var(--green)" />
    <State x={400} y={78} w={184} label="awaiting-owner" sub="first contact, or ask-me" tone="var(--amber)" />
    <State x={400} y={146} w={184} label="request_denied" sub="weakened echo · bad sig · policy" tone="var(--red)" />

    <Edge x1={396} y1={56} x2={400} y2={38} tone="var(--green)" />
    <Edge x1={396} y1={56} x2={400} y2={100} tone="var(--amber)" />
    <Edge x1={266} y1={78} x2={400} y2={168} tone="var(--red)" />

    {/* What the owner's answer does to a held ticket. */}
    <text x={16} y={214} fill="var(--ink-3)" fontSize="10.5" fontFamily={MONO} letterSpacing="1">
      WHILE AWAITING-OWNER — THE TICKET ROTATES ON EVERY POLL
    </text>
    {[
      ["she approves", "granted", "var(--green)", 16],
      ["she denies", "request_denied", "var(--red)", 212],
      ["it expires", "invalid_grant", "var(--ink-3)", 408],
    ].map(([why, to, tone, x]) => (
      <g key={to}>
        <text x={x} y={244} fill="var(--ink-2)" fontSize="10.5">
          {why}
        </text>
        <State x={x} y={252} w={172} label={to} tone={tone} />
      </g>
    ))}

    <text x={16} y={294} fill="var(--ink-3)" fontSize="10">
      Approving a first contact also records the standing connection.
    </text>
  </Frame>
);

// ---------------------------------------------------------------------------

const diagrams = {
  "ticket-lifecycle": { Draw: TicketLifecycle, title: "Ticket lifecycle" },
  "four-beats": { Draw: FourBeats, scenes: fourBeatScenes, title: "The four beats" },
  "trust-boundary": {
    Draw: TrustBoundary,
    scenes: trustBoundaryScenes,
    title: "The trust boundary",
  },
  "discovery-layers": {
    Draw: DiscoveryLayers,
    scenes: discoveryScenes,
    title: "Public and protected discovery",
  },
  "terms-exchange": { Draw: TermsExchange, scenes: termsScenes, title: "The terms exchange" },
  "proof-of-possession": {
    Draw: PopKey,
    scenes: popScenes,
    title: "Proof-of-possession",
  },
  "two-intents": {
    Draw: Register,
    scenes: registerScenes,
    title: "One agent, as it appears in the owner's own record",
  },
  "identity-vs-authz": {
    Draw: IdentityVsAuthz,
    scenes: identityScenes,
    title: "Identity is not authorization",
  },
  "revoke-cascade": {
    Draw: RevokeCascade,
    scenes: revokeScenes,
    title: "Revocation",
  },
  "roles-map": { Draw: RolesMap, scenes: rolesScenes, title: "The six roles" },
  "two-hosts": {
    Draw: TwoHosts,
    scenes: twoHostsScenes,
    title: "One core, two hosts",
  },
  "rogue-challenge": {
    Draw: RogueChallenge,
    scenes: rogueScenes,
    title: "A challenge you must not trust",
  },
  "standards-map": { Draw: StandardsMap, scenes: standardsScenes, title: "The standards" },
  "compare-uma": { Draw: CompareUma, scenes: compareUmaScenes, title: "Keep, change, add" },
  "enforcement-order": {
    Draw: EnforcementOrder,
    scenes: enforcementScenes,
    title: "The enforcement order",
  },
  "single-use-race": {
    Draw: SingleUseRace,
    scenes: singleUseScenes,
    title: "Two replicas, one grant",
  },
  "who-answers": {
    Draw: WhoAnswers,
    scenes: whoAnswersScenes,
    title: "Who has standing to answer",
  },
};

const DocDiagram = ({ name, caption }) => {
  // The two figures that are operated rather than watched.
  if (name === "pend-sandbox") return <DocSandbox caption={caption} />;
  if (name === "wire-inspector") return <DocInspector caption={caption} />;

  const chosen = diagrams[name];
  if (!chosen) return null;
  const { Draw, scenes, title } = chosen;
  return (
    <DocFigure title={title || name} scenes={scenes} caption={caption}>
      <Draw />
    </DocFigure>
  );
};

export default DocDiagram;

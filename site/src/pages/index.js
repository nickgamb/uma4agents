import React, { useEffect, useRef, useState } from "react";
import Layout from "../components/Layout";
import SEO from "../components/SEO";
import { SCENES, mount, prefersReducedMotion } from "../animation/story";
import ArchitectureStage from "../animation/ArchitectureStage";
import "../style/stage.css";

/**
 * The home page is the explanation.
 *
 * React owns the markup; the scene machine in ../animation/story.js owns only
 * the motion, and is attached to this element after mount. The captions are
 * rendered from the same SCENES array that drives the animation, so the words
 * and the pictures cannot drift apart — and the full list is in the document
 * whether or not anything ever moves.
 */
const IndexPage = () => {
  const stageRef = useRef(null);
  const [scene, setScene] = useState(0);
  const [still, setStill] = useState(false);

  useEffect(() => {
    setStill(prefersReducedMotion());
    if (!stageRef.current) return undefined;
    return mount(stageRef.current, setScene);
  }, []);

  const current = SCENES[scene] || SCENES[0];

  return (
    <Layout>
      <section className="stage-band" ref={stageRef}>
        <div className="stage-wrap">
        <svg className="stage" viewBox="0 175 1200 465" role="img"
                 aria-labelledby="stage-title stage-desc">
              <title id="stage-title">How UMA for Agents works</title>
              <desc id="stage-desc">Alice sets her access terms and goes offline. Bob's
                AI agent is refused by her vault and given a ticket, takes the ticket to
                Alice's authorization server, is handed her terms, signs them, and is
                granted scoped access. For a trade, her phone buzzes and she approves one
                single-use key.</desc>

              <defs>
                <linearGradient id="mark" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="var(--accent)"/>
                  <stop offset="1" stopColor="var(--agent)"/>
                </linearGradient>
                <radialGradient id="glow1" cx="0.5" cy="0.5" r="0.5">
                  <stop offset="0" stopColor="var(--stage-glow)" stopOpacity="0.10"/>
                  <stop offset="1" stopColor="var(--stage-glow)" stopOpacity="0"/>
                </radialGradient>
                <radialGradient id="glow2" cx="0.5" cy="0.5" r="0.5">
                  <stop offset="0" stopColor="var(--stage-glow)" stopOpacity="0.08"/>
                  <stop offset="1" stopColor="var(--stage-glow)" stopOpacity="0"/>
                </radialGradient>

                {/* Arrowheads for act two's flows. */}
        <marker id="mAccent" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--accent)"/>
        </marker>
        <marker id="mGreen" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--green)"/>
        </marker>
        <marker id="mWarn" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--amber)"/>
        </marker>

        {/* Actors wait offstage at x=-140, which is outside the viewBox but
                     not outside the element: when the element is wider than the
                     viewBox's aspect ratio the drawing is letterboxed, and anything
                     beyond the viewBox renders happily into the side bands. So the
                     wings have to be drawn shut explicitly. */}
                <clipPath id="stage-clip">
                  <rect x="0" y="175" width="1200" height="465"/>
                </clipPath>
              </defs>

              <g clipPath="url(#stage-clip)">
              <rect x="0" y="175" width="1200" height="465" fill="url(#glow1)"/>
              <rect x="200" y="220" width="1000" height="420" fill="url(#glow2)"/>
              {/* Act one's set, as one thing. Act two hides it wholesale rather
            than each scene remembering to fade nine props individually —
            which is the sort of list that is right the day it is written and
            wrong the day something is added to it. */}
        <g id="story">
        <path d="M40 560 H1160" className="ground"/>

              {/* ===================== PLACES (they don't move) ==================== */}

              <g id="place-home" transform="translate(150 560)">
                <rect x="-92" y="-60" width="184" height="16" rx="5" className="desk"/>
                <rect x="-46" y="-72" width="92" height="12" rx="3" className="panel-2"/>
                {/* The lid's hinge is the static translate; the rotation goes on the
                     inner group, because the timeline overwrites whatever transform
                     it animates. */}
                <g transform="translate(-46 -72)">
                  <g id="laptop-lid">
                    <rect id="laptop-screen" x="0" y="-58" width="92" height="58" rx="4" className="screen"/>
                  </g>
                </g>
                <text x="0" y="42" className="place-label">ALICE</text>
                <text x="0" y="60" className="place-sublabel">an owner, not an operator</text>
              </g>

              <g id="place-nightstand" transform="translate(300 560)" opacity="0">
                <rect x="-34" y="-46" width="68" height="46" rx="6" className="desk"/>
                <rect x="-26" y="-98" width="52" height="94" rx="9" className="phone-body"/>
                <rect id="phone-screen" x="-20" y="-91" width="40" height="76" rx="4" className="phone-screen"/>
                <g id="buzz" opacity="0">
                  <path d="M-42 -122 q-10 -10 0 -20 M42 -122 q10 -10 0 -20" className="buzz-line"/>
                  <path d="M-56 -112 q-16 -16 0 -34 M56 -112 q16 -16 0 -34" className="buzz-line"/>
                </g>
              </g>

              {/* Where her policy lives, and answers, while she is asleep. */}
              <g id="place-as" transform="translate(700 560)">
                <rect x="-80" y="-150" width="160" height="150" rx="12" className="panel"/>
                <path d="M-80 -150 L0 -196 L80 -150 Z" className="roof"/>
                <path id="as-shield" d="M0 -128 l30 12 v22 q0 26 -30 38 q-30 -12 -30 -38 v-22 z" className="shield"/>
                <path d="M-12 -96 l9 10 l17 -19" className="tick"/>
                <text x="0" y="42" className="place-label">HER AUTHORIZATION SERVER</text>
                <text x="0" y="60" className="place-sublabel">her policy, her side</text>
              </g>

              {/* The resource server. Not "Alice's vault": it is her brokerage's,
                   and it holds many clients' holdings in one place — which is why the
                   authority over hers cannot live here. Every row is someone's; only
                   the lit one is Alice's, and only that row is what her authorization
                   server has anything to say about. The others belong to owners who
                   have their own policy, somewhere else. */}
              <g id="place-vault" transform="translate(1040 560)">
                <rect x="-92" y="-228" width="184" height="228" rx="12" className="panel"/>

                <g className="tenant-row">
                  <rect x="-76" y="-212" width="152" height="42" rx="6" className="panel-2"/>
                  <circle cx="-56" cy="-191" r="7" className="tenant-dot"/>
                  <path d="M-38 -197 H50 M-38 -185 H24" className="tenant-line"/>
                </g>

                {/* Alice's. */}
                <g id="alice-row">
                  <rect x="-76" y="-162" width="152" height="42" rx="6" className="own-row"/>
                  <circle cx="-56" cy="-141" r="7" className="own-dot"/>
                  <path d="M-38 -147 H50 M-38 -135 H30" className="own-line"/>
                  <text x="-76" y="-168" className="own-label">ALICE'S HOLDINGS</text>
                </g>

                <g className="tenant-row">
                  <rect x="-76" y="-112" width="152" height="42" rx="6" className="panel-2"/>
                  <circle cx="-56" cy="-91" r="7" className="tenant-dot"/>
                  <path d="M-38 -97 H50 M-38 -85 H38" className="tenant-line"/>
                </g>
                <g className="tenant-row">
                  <rect x="-76" y="-62" width="152" height="42" rx="6" className="panel-2"/>
                  <circle cx="-56" cy="-41" r="7" className="tenant-dot"/>
                  <path d="M-38 -47 H50 M-38 -35 H18" className="tenant-line"/>
                </g>

                {/* The lock sits on Alice's row, because that is the only row this
                     story is about. */}
                <g transform="translate(56 -141)">
                  <circle cx="0" cy="0" r="15" className="vault-dial"/>
                  <path id="vault-spokes" d="M0 -15 V15 M-15 0 H15 M-10.6 -10.6 L10.6 10.6 M10.6 -10.6 L-10.6 10.6"
                        className="vault-spokes"/>
                  <circle cx="0" cy="0" r="4" className="vault-hub"/>
                </g>

                <text x="0" y="42" className="place-label">MERIDIAN WEALTH · RESOURCE SERVER</text>
                <text x="0" y="60" className="place-sublabel">many owners, one server</text>

                <g id="vault-no" opacity="0">
                  <circle cx="0" cy="-141" r="40" className="ring-no"/>
                  <path d="M-16 -157 L16 -125 M16 -157 L-16 -125" className="cross-no"/>
                </g>
                <g id="vault-yes" opacity="0">
                  <circle cx="0" cy="-141" r="40" className="ring-yes"/>
                  <path d="M-18 -141 l13 14 l24 -27" className="check-yes"/>
                </g>
              </g>

              {/* ===================== ACTORS (they move) ========================== */}
              {/* No `transform` attribute on any of these. The timeline composes
                   their transform from x/y, and an attribute here would be replaced
                   the first time one of them moved — putting the actor at the origin
                   instead of on the ground. Their starting marks are in u4a.js, with
                   the rest of the blocking. */}

              <g id="alice">
                <circle cx="0" cy="-86" r="14" className="fig head"/>
                <path d="M-15 -90a15 15 0 0 1 30 0q-9 -7 -15 -4q-6 -3 -15 4z" className="hair"/>
                <path d="M0 -72 V-32" className="fig"/>
                <path id="alice-arm-l" d="M0 -63 L-21 -46" className="fig arm-l"/>
                <path id="alice-arm-r" d="M0 -63 L21 -46" className="fig arm-r"/>
                <path d="M0 -32 L-15 0" className="fig"/>
                <path d="M0 -32 L15 0" className="fig"/>
              </g>

              <g id="bob">
                <circle cx="0" cy="-86" r="14" className="fig head"/>
                <path d="M-14 -93q14 -9 28 0" className="hair"/>
                <path d="M0 -72 V-32" className="fig"/>
                <path d="M0 -70 l-5 5 l5 17 l5 -17 z" className="tie"/>
                <path d="M0 -63 L-21 -46" className="fig"/>
                <path d="M0 -63 L21 -46" className="fig"/>
                <path d="M0 -32 L-15 0" className="fig"/>
                <path d="M0 -32 L15 0" className="fig"/>
              </g>

              {/* Bob's agent. Deliberately a small, polite machine: the point of the
                   whole protocol is that it is not the villain — it is simply not
                   Alice, and that is enough to need a negotiation. */}
              <g id="agent">
                <path d="M0 -99 V-90" className="fig"/>
                <circle cx="0" cy="-102" r="4" className="bot-dot"/>
                <rect x="-20" y="-90" width="40" height="31" rx="10" className="bot-head"/>
                <circle className="eye" cx="-7.5" cy="-74" r="3.6"/>
                <circle className="eye" cx="7.5" cy="-74" r="3.6"/>
                <rect x="-15" y="-55" width="30" height="31" rx="9" className="bot-body"/>
                <path d="M-15 -45 L-28 -35" className="fig"/>
                <path d="M15 -45 L28 -35" className="fig"/>
                <path d="M-7 -24 V0" className="fig"/>
                <path d="M7 -24 V0" className="fig"/>
              </g>

              {/* Alice's own personal AI. Deliberately the same machine as Bob's
                   in shape and different in colour: it is the same kind of thing,
                   on the other side of the boundary. It never talks to Bob's
                   agent — it only ever answers her authorization server. */}
              <g id="alice-ai">
                <path d="M0 -99 V-90" className="fig"/>
                <circle cx="0" cy="-102" r="4" className="own-ai-dot"/>
                <rect x="-20" y="-90" width="40" height="31" rx="10" className="own-ai-head"/>
                <circle className="own-ai-eye" cx="-7.5" cy="-74" r="3.6"/>
                <circle className="own-ai-eye" cx="7.5" cy="-74" r="3.6"/>
                <rect x="-15" y="-55" width="30" height="31" rx="9" className="own-ai-body"/>
                <path d="M-15 -45 L-28 -35" className="fig"/>
                <path d="M15 -45 L28 -35" className="fig"/>
                <path d="M-7 -24 V0" className="fig"/>
                <path d="M7 -24 V0" className="fig"/>
                <path id="alice-ai-key" d="M0 -112 m-6 0 a6 6 0 1 0 12 0 a6 6 0 1 0 -12 0 M6 -112 H18 M14 -112 V-106"
                      className="own-ai-key" opacity="0"/>
              </g>

              {/* The setup's question: someone is going to ask for her holdings, and
                   the server holding them is not the party who can answer. */}
              <g id="question" opacity="0">
                <circle cx="0" cy="0" r="30" className="q-ring"/>
                <text x="0" y="12" className="q-mark">?</text>
              </g>

              {/* The permission ticket: the handle the whole negotiation hangs on. */}
              <g id="ticket" opacity="0">
                <path d="M-40 -22 h80 v13 a9 9 0 0 0 0 18 v13 h-80 v-13 a9 9 0 0 0 0 -18 z"
                      className="ticket"/>
                <path d="M-22 -4 H22 M-22 8 H10" className="ticket-line"/>
              </g>

              {/* The terms she proffers. */}
              <g id="scroll" opacity="0">
                <rect x="-62" y="-44" width="124" height="88" rx="7" className="paper"/>
                <path d="M-44 -22 H44 M-44 -6 H44 M-44 10 H30 M-44 26 H16" className="paper-line"/>
              </g>

              <g id="signature" opacity="0">
                <path id="sign-line" d="M-40 34 q10 -20 20 0 t20 -2 t18 -6" className="sign-line"/>
              </g>

              {/* The single-use grant. It is a key, and it is going to break. */}
              <g id="key" opacity="0">
                <circle cx="-20" cy="0" r="14" className="key-ring"/>
                <path d="M-6 0 H34 M24 0 V12 M34 0 V14" className="key-blade"/>
              </g>

              <g id="ledger" opacity="0">
                <rect x="-210" y="-92" width="420" height="184" rx="12" className="panel"/>
                <text x="-182" y="-56" className="ledger-head">THE LEDGER</text>
                <g className="ledger-row"><text x="-182" y="-16">promised</text><text x="50" y="-16" className="ledger-v">terms, signed</text></g>
                <g className="ledger-row"><text x="-182" y="20">touched</text><text x="50" y="20" className="ledger-v">what it read</text></g>
                <g className="ledger-row"><text x="-182" y="56">approved</text><text x="50" y="56" className="ledger-v">the one trade</text></g>
              </g>

              </g>

        <ArchitectureStage />

        <g id="titlecard" opacity="0">
                <rect x="0" y="175" width="1200" height="465" className="curtain"/>
                <g transform="translate(600 380)">
                  <rect x="-25" y="-104" width="50" height="50" rx="13" fill="url(#mark)"/>
                  <text x="0" y="-68" className="mark-glyph">U</text>
                  <text x="0" y="6" className="title">UMA for Agents</text>
                  <text x="0" y="54" className="subtitle">She isn’t online. Her policy is.</text>
                </g>
              </g>
              </g>
            </svg>
        </div>

        {!still && (
          <>
            <p className="stage-caption" aria-live="polite">
              {current.beat && <span className="beat">{current.beat}</span>}
              {current.text}
            </p>

            <div className="stage-controls">
              <button className="stage-toggle" type="button" aria-label="Pause">
                Pause
              </button>
              <input
                className="stage-scrub"
                type="range"
                min="0"
                max="1000"
                defaultValue="0"
                step="1"
                aria-label="Scrub the animation"
              />
              <button
                className="stage-replay"
                type="button"
                aria-label="Replay from the start"
              >
                Replay
              </button>
            </div>
          </>
        )}

        {/* The story as text. Always in the document — it is the whole
            explanation for anyone who cannot or would rather not watch it
            move, and it is what a screen reader and a crawler get. */}
        <ol className={`storyboard${still ? " storyboard--shown" : ""}`}>
          {SCENES.filter((s) => s.text).map((s) => (
            <li key={s.at}>
              {s.beat && <b>{s.beat}. </b>}
              {s.text}
            </li>
          ))}
        </ol>
      </section>
    </Layout>
  );
};

export const Head = () => (
  <SEO
    title="UMA for Agents — may your agent touch my stuff?"
    description="Alice sets her terms once. Other people's agents negotiate against them — while she is offline. An animated explanation, and a lab you can run."
    pathname="/"
  />
);

export default IndexPage;

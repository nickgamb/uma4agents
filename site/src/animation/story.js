/* The story, as a sequence of scenes.
 *
 * One cast on one stage; the scenes are camera directions rather than
 * separate drawings, so the agent's walk from the resource server to Alice's
 * authorization server and back is the same motion the protocol describes.
 *
 * Why a scene machine and not one long timeline
 * ---------------------------------------------
 * The obvious build is a single anime timeline with every move placed on it
 * by absolute time. It does not survive contact with this story, because
 * anime composes animations per property: adding a second tween for the same
 * property of the same element to one timeline silently discards it. The
 * agent's opacity changes five times here and its position eight times, so
 * most of the story would quietly never play — and it would look like it
 * worked, because the first tween for each property still runs.
 *
 * So each scene declares two things instead: `end`, what it leaves changed
 * when it finishes, and `play`, the motion within it. Playing a scene means
 * applying the accumulated state and issuing fresh `animate()` calls, which
 * compose correctly because they are separate animations rather than entries
 * in one timeline. Scrubbing becomes exact and cheap: to show any moment,
 * apply the base state plus every earlier scene's `end`.
 *
 * The captions are the authoritative text. The page renders them as an
 * ordered list whatever happens, so it explains itself with the animation
 * switched off, with JavaScript disabled, and to a screen reader. The
 * animation illustrates the words; it does not carry meaning the words lack.
 *
 * `mount(root)` wires the machine to an already-rendered DOM and returns a
 * teardown, so React owns the markup and this owns only the motion.
 */

import { animate as tween, utils } from "animejs";

/* The animation's colours, as tokens rather than values.
 *
 * anime interpolates between concrete values and cannot read a var(), so the
 * obvious thing is to resolve the palette here at module load. That was what
 * this did, and it is wrong once the site has two themes: the scene data below
 * is a pile of object literals, so every colour would be frozen at import into
 * whichever theme happened to be active first, and a reader who switched would
 * get a half-repainted stage.
 *
 * So `C.rest` is the string "@rest", and the two places a value actually
 * reaches the DOM — `paint` on the way into `utils.set`, and the `animate`
 * wrapper below — swap tokens for live colours read from the document. The
 * scenes stay declarative, nothing is captured, and a theme change is just
 * "read the properties again and replay the current scene". */
const C = {
  rest:    "@rest",       // the resting / identity colour
  granted: "@granted",
  pending: "@pending",
  agent:   "@agent",
  sunken:  "@sunken",
  edge:    "@edge",
  own:     "@own",     // her own AI: her colour, not the requesting side's
};

/* Filled by readTheme(), which runs before the first frame and again whenever
   the theme changes. */
let PALETTE = {};

const VARS = {
  rest: "--accent",
  granted: "--green",
  pending: "--amber",
  agent: "--agent",
  sunken: "--sunken",
  edge: "--edge",
  own: "--primary",
};

function readTheme() {
  if (typeof window === "undefined") return;
  const cs = getComputedStyle(document.documentElement);
  PALETTE = Object.fromEntries(
    Object.entries(VARS).map(([k, v]) => [k, cs.getPropertyValue(v).trim()])
  );
}

/** Swap "@token" for the live colour, through arrays and property bags. */
const paint = (v) =>
  typeof v === "string" && v.charCodeAt(0) === 64
    ? PALETTE[v.slice(1)] || v
    : Array.isArray(v)
    ? v.map(paint)
    : v;

const painted = (props) =>
  Object.fromEntries(Object.entries(props).map(([k, v]) => [k, paint(v)]));

/* The scenes below call this rather than anime's own `animate`, so a tween
   written as [C.rest, C.granted] arrives as two real colours. */
const animate = (targets, props) => tween(targets, painted(props));

/* Where everyone stands. Named so the scenes read as blocking notes. */
const HOME = 240;
const OFFSTAGE_L = -140;
const PHONE_MARK = 372;        // beside the nightstand, reaching for it
const BOB_MARK = 470;
/* Her own AI stands between her home and her authorization server — her side
   of the stage, and clear of the nightstand she left the phone on. */
const OWN_MARK = 452;
const AGENT_MARK = BOB_MARK + 92;
/* Structures are wide; an actor stands beside one, not inside it. These are
   the marks the agent walks to, offset left of each building's centre. */
const AS_CENTRE = 700;
const AS_MARK = AS_CENTRE - 112;
const VAULT_CENTRE = 1040;
const VAULT_MARK = VAULT_CENTRE - 140;
const VAULT_STEP = VAULT_MARK - 66;   // bounced back from the door
const GROUND = 560;

/* The stage before anything happens. Every property any scene ever touches
 * appears here, so that "put it back how it started" is a fact about this
 * object rather than a list of resets someone has to remember to update. */
const BASE = {
  '#alice':            { x: HOME, y: GROUND, opacity: 1 },
  '#alice-arm-l':      { rotate: 0 },
  '#bob':              { x: OFFSTAGE_L, y: GROUND, opacity: 0 },
  '#agent':            { x: OFFSTAGE_L - 90, y: GROUND, opacity: 0 },
  '#alice-ai':         { x: OWN_MARK, y: GROUND, opacity: 0 },
  '#alice-ai-key':     { opacity: 0 },
  '#alice-ai .own-ai-eye': { fill: C.own, opacity: 1 },
  '#agent .eye':       { fill: C.rest, opacity: 1 },
  '#ticket':           { x: VAULT_MARK, y: GROUND - 128, opacity: 0 },
  '#scroll':           { x: AS_MARK, y: GROUND - 250, opacity: 0, scaleY: 1 },
  '#signature':        { x: AS_CENTRE, y: GROUND - 236, opacity: 0 },
  '#key':              { x: AS_CENTRE, y: GROUND - 230, opacity: 0, rotate: 0, scale: 1 },
  '#ledger':           { x: 600, y: 400, opacity: 0 },
  '#titlecard':        { opacity: 0 },
  '#laptop-lid':       { rotate: 0 },
  '#laptop-screen':    { stroke: C.rest },
  '#place-nightstand': { opacity: 0 },
  '#phone-screen':     { fill: C.sunken },
  '#buzz':             { opacity: 0 },
  '#as-shield':        { stroke: C.rest },
  '#vault-spokes':     { rotate: 0 },
  '#vault-no':         { opacity: 0, scale: 1 },
  '#vault-yes':        { opacity: 0, scale: 1 },
  '#alice-row':        { opacity: 0.25 },
  '#alice-row .own-row': { stroke: C.edge },
  '#question':         { x: VAULT_CENTRE, y: GROUND - 300, opacity: 0, scale: 1 },

  // Act two. The story's cast and the machine share one stage, so each act
  // hides the other rather than the page swapping drawings.
  '#story':            { opacity: 1 },
  '#arch':             { opacity: 0 },
  '#ns-bob':           { opacity: 0 },
  '#ns-edge':          { opacity: 0 },
  '#ns-meridian':      { opacity: 0 },
  '#ns-alice':         { opacity: 0 },
  '#arch-agent':       { opacity: 0 },
  '#arch-operator':    { opacity: 0 },
  '#arch-edge':        { opacity: 0 },
  '#arch-agw':         { opacity: 0 },
  '#arch-pep':         { opacity: 0 },
  '#arch-vault':       { opacity: 0 },
  '#arch-as':          { opacity: 0 },
  '#arch-db':          { opacity: 0 },
  '#arch-keycloak':    { opacity: 0 },
  '#arch-portal':      { opacity: 0 },
  '#arch-mesh':        { opacity: 0 },
  '#beat-1':           { opacity: 0 },
  '#beat-2':           { opacity: 0 },
  '#beat-4':           { opacity: 0 },
  '#arch-denied':      { opacity: 0, scale: 1 },
  '#arch-scale':       { opacity: 0 },
};

/* Each scene declares only two things:
 *
 *   `end`  — what this scene leaves changed when it finishes. Nothing else.
 *   `play` — the motion within it.
 *
 * The stage at the start of scene i is the base plus every earlier scene's
 * `end`, in order. That is the whole state model, and it is worth being
 * strict about: the first draft had each scene restate the entire world it
 * expected to find, which duplicated every fact a dozen times and got four
 * of them wrong — a ticket that stayed in frame for the rest of the story, a
 * phone left glowing green through the credits. A scene cannot know what
 * came before it. It can only be honest about what it leaves behind.
 */
export const SCENES = [
  {
    at: 0,
    text: 'Alice\u2019s money sits at her brokerage \u2014 in a system that holds a thousand other clients\u2019 holdings too.',
    end: { '#alice-row': { opacity: 1 }, '#alice-row .own-row': { stroke: C.rest } },
    play() {
      animate('#alice-row', { opacity: [0.25, 1], duration: 900, ease: 'outQuad' });
      animate('#alice-row .own-row', { stroke: [C.edge, C.rest], duration: 900, ease: 'outQuad' });
    },
  },
  {
    at: 5000,
    text: 'Her new advisor\u2019s agent is going to come asking for it. The brokerage cannot answer for her \u2014 and she will not always be awake.',
    end: {},
    play() {
      animate('#question', { opacity: [0, 1], y: [GROUND - 270, GROUND - 300], duration: 700, ease: 'outBack' });
      animate('#question', { scale: [1, 1.08, 1], duration: 1100, loop: 2, delay: 800 });
      animate('#question', { opacity: [1, 0], duration: 500, delay: 3900 });
    },
  },
  {
    at: 10000,
    text: 'So she writes her terms once \u2014 what an agent may see, for what purpose, for how long.',
    end: {},
    play() {
      // her hand at the keys
      animate('#alice-arm-l', { rotate: [0, 15, 0], duration: 640, loop: 3, ease: 'inOutSine' });
      animate('#laptop-screen', { stroke: [C.rest, C.agent, C.rest], duration: 1700, loop: 2 });
    },
  },
  {
    at: 15200,
    text: 'Then she closes the laptop. Nothing that follows waits for her to open it again.',
    end: { '#laptop-lid': { rotate: 82 }, '#alice': { x: OFFSTAGE_L },
           '#place-nightstand': { opacity: 1 } },
    play() {
      animate('#laptop-lid', { rotate: [0, 82], duration: 900, ease: 'inOutBack' });
      animate('#alice', { x: [HOME, OFFSTAGE_L], duration: 2500, delay: 900, ease: 'inOutSine' });
      animate('#place-nightstand', { opacity: [0, 1], duration: 700, delay: 1600 });
    },
  },
  {
    at: 20200,
    text: 'Bob is that advisor. His firm works through an agent, and it needs her portfolio.',
    end: { '#bob': { x: BOB_MARK, opacity: 1 }, '#agent': { x: AGENT_MARK, opacity: 1 } },
    play() {
      animate('#bob', { opacity: [0, 1], x: [OFFSTAGE_L, BOB_MARK], duration: 2000, ease: 'outSine' });
      animate('#agent', { opacity: [0, 1], x: [OFFSTAGE_L - 90, AGENT_MARK], duration: 2100, delay: 150, ease: 'outSine' });
      animate('#agent .eye', { opacity: [1, 0.25, 1], duration: 520, loop: 3, delay: 2300 });
    },
  },
  {
    at: 25200,
    beat: 'Beat 1 \u00b7 challenge',
    text: 'The server refuses it \u2014 and hands it a ticket, with the address of Alice\u2019s authorization server.',
    end: { '#agent': { x: VAULT_STEP }, '#ticket': { x: VAULT_STEP, opacity: 1 } },
    play() {
      animate('#agent', { x: [AGENT_MARK, VAULT_MARK], duration: 2100, ease: 'inOutSine' });
      animate('#agent', { y: [GROUND, GROUND - 14, GROUND], duration: 340, loop: 2, delay: 2200 });
      animate('#vault-no', { opacity: [0, 1], scale: [0.6, 1], duration: 520, delay: 2800, ease: 'outBack' });
      animate('#agent', { x: [VAULT_MARK, VAULT_STEP], duration: 480, delay: 2900, ease: 'outQuad' });
      animate('#ticket', {
        opacity: [0, 1], x: [VAULT_CENTRE - 70, VAULT_STEP],
        y: [GROUND - 200, GROUND - 128], duration: 900, delay: 3200, ease: 'outQuad',
      });
      animate('#vault-no', { opacity: [1, 0], duration: 500, delay: 4900 });
    },
  },
  {
    at: 31000,
    beat: 'Beat 2 \u00b7 the terms',
    text: 'The agent takes the ticket to her server. She isn\u2019t there. Her terms are.',
    end: { '#agent': { x: AS_MARK }, '#ticket': { opacity: 0 }, '#scroll': { opacity: 1 } },
    play() {
      animate(['#agent', '#ticket'], { x: AS_MARK, duration: 2200, ease: 'inOutSine' });
      animate('#ticket', { opacity: [1, 0], duration: 400, delay: 2300 });
      animate('#scroll', {
        opacity: [0, 1], scaleY: [0.06, 1], y: [GROUND - 190, GROUND - 250],
        duration: 800, delay: 2500, ease: 'outBack',
      });
      animate('#as-shield', { stroke: [C.rest, C.granted, C.rest], duration: 1500, delay: 2800 });
    },
  },
  {
    at: 36800,
    beat: 'Beat 3 \u00b7 commit',
    text: 'The agent signs them, or it walks away. There is no third option and no haggling.',
    end: { '#scroll': { opacity: 0 }, '#signature': { opacity: 0 },
           '#agent .eye': { fill: C.granted } },
    play() {
      animate('#signature', { opacity: [0, 1], duration: 200 });
      animate('#sign-line', { strokeDasharray: ['0 200', '200 0'], duration: 1100, ease: 'outQuad' });
      animate('#agent .eye', { fill: [C.rest, C.granted], duration: 600, delay: 1200 });
      animate(['#scroll', '#signature'], { opacity: [1, 0], duration: 600, delay: 3400 });
    },
  },
  {
    at: 41600,
    beat: 'Beat 4 \u00b7 grant',
    text: 'Signed, it is let in \u2014 for that purpose, for that long, and no further. Alice is still asleep.',
    end: { '#agent': { x: VAULT_MARK, opacity: 1 }, '#vault-spokes': { rotate: 200 } },
    play() {
      animate('#agent', { x: [AS_MARK, VAULT_MARK], duration: 1900, ease: 'inOutSine' });
      animate('#vault-yes', { opacity: [0, 1], scale: [0.6, 1], duration: 560, delay: 2000, ease: 'outBack' });
      animate('#vault-spokes', { rotate: [0, 200], duration: 1200, delay: 2000, ease: 'inOutQuad' });
      animate('#agent', { x: [VAULT_MARK, VAULT_MARK + 62], opacity: [1, 0.3], duration: 800, delay: 2600 });
      animate('#vault-yes', { opacity: [1, 0], duration: 400, delay: 4200 });
      animate('#agent', { x: [VAULT_MARK + 62, VAULT_MARK], opacity: [0.3, 1], duration: 700, delay: 4400 });
    },
  },
  {
    at: 47200,
    text: 'Then it asks to sell something. Her policy says: not this one. Ask me.',
    end: { '#vault-no': { opacity: 1 }, '#as-shield': { stroke: C.pending },
           '#agent .eye': { fill: C.pending } },
    play() {
      animate('#agent', { y: [GROUND, GROUND - 14, GROUND], duration: 340, loop: 2 });
      animate('#vault-no', { opacity: [0, 1], scale: [0.6, 1], duration: 500, delay: 700, ease: 'outBack' });
      animate('#as-shield', { stroke: [C.rest, C.pending], duration: 700, delay: 1300 });
      animate('#agent .eye', { fill: [C.granted, C.pending], duration: 500, delay: 1500 });
    },
  },
  {
    at: 52400,
    text: 'Her phone buzzes. She approves that one order, from the couch.',
    end: { '#phone-screen': { fill: C.granted } },
    play() {
      animate('#phone-screen', { fill: [C.sunken, C.pending, C.sunken], duration: 900, loop: 3 });
      animate('#buzz', { opacity: [0, 1, 0], duration: 900, loop: 3 });
      animate('#alice', { x: [OFFSTAGE_L, PHONE_MARK], duration: 1700, delay: 500, ease: 'outSine' });
      animate('#alice-arm-l', { rotate: [0, -32, 0], duration: 700, delay: 2400 });
      animate('#phone-screen', { fill: [C.sunken, C.granted], duration: 400, delay: 2900 });
      animate('#alice', { x: [PHONE_MARK, OFFSTAGE_L], duration: 2100, delay: 3500, ease: 'inSine' });
    },
  },
  {
    at: 58000,
    text: 'The key she grants opens the door once, for that trade, and then it is spent.',
    end: { '#vault-no': { opacity: 0 }, '#vault-spokes': { rotate: 380 },
           '#agent .eye': { fill: C.rest }, '#as-shield': { stroke: C.rest },
           '#phone-screen': { fill: C.sunken } },
    play() {
      animate('#key', {
        opacity: [0, 1], x: [AS_CENTRE, VAULT_CENTRE - 60],
        y: [GROUND - 230, GROUND - 150], rotate: [0, 380],
        duration: 1400, ease: 'outQuad',
      });
      animate('#vault-no', { opacity: [1, 0], duration: 300, delay: 1200 });
      animate('#vault-yes', { opacity: [0, 1], scale: [0.6, 1], duration: 500, delay: 1400, ease: 'outBack' });
      animate('#vault-spokes', { rotate: [200, 380], duration: 1000, delay: 1400 });
      // and then it is spent
      animate('#key', { scale: [1, 1.3, 0], opacity: [1, 1, 0], duration: 1000, delay: 2800, ease: 'inBack' });
      animate('#vault-yes', { opacity: [1, 0], duration: 400, delay: 4200 });
      animate('#agent .eye', { fill: [C.pending, C.rest], duration: 400, delay: 4200 });
      animate('#as-shield', { stroke: [C.pending, C.rest], duration: 400, delay: 4200 });
      animate('#phone-screen', { fill: [C.granted, C.sunken], duration: 400, delay: 4200 });
    },
  },
  {
    at: 63400,
    text: 'And all of it is written down on her side: what was promised, what was touched, what she personally approved.',
    end: { '#agent': { opacity: 0.16 }, '#bob': { opacity: 0.16 } },
    play() {
      animate(['#agent', '#bob'], { opacity: [1, 0.16], duration: 700 });
      animate('#ledger', { opacity: [0, 1], y: [432, 400], duration: 800, delay: 300, ease: 'outBack' });
      animate('#ledger .ledger-row', {
        opacity: [0, 1], x: [-24, 0], duration: 520, delay: (_, i) => 800 + i * 380,
      });
      animate('#ledger', { opacity: [1, 0], duration: 700, delay: 4400 });
    },
  },
  {
    at: 68600,
    beat: null,
    text: 'That is the whole protocol. Four beats, one owner, one agent that is not hers.',
    end: {},
    play() {
      animate('#titlecard', { opacity: [0, 1], duration: 900 });
      animate(['#agent', '#bob'], { opacity: [0.16, 0], duration: 500, delay: 1200 });
      animate('#titlecard', { opacity: [1, 0], duration: 800, delay: 2900 });
    },
  },
  {
    at: 73000,
    beat: 'But what if Alice has one too?',
    text: 'Nothing in those four beats required Alice to be a person at a laptop. The side that decides needs an authority and a way to reach her — and both can sit on something she owns.',
    end: { '#alice': { x: HOME, opacity: 1 }, '#alice-ai': { opacity: 1 },
           '#agent': { opacity: 0 }, '#bob': { opacity: 0 } },
    play() {
      animate(['#agent', '#bob'], { opacity: [0.16, 0], duration: 500 });
      animate('#alice', { x: [OFFSTAGE_L, HOME], duration: 1400, ease: 'outSine' });
      animate('#alice-ai', {
        opacity: [0, 1], x: [OWN_MARK - 52, OWN_MARK], duration: 900, delay: 1200, ease: 'outBack',
      });
      animate('#alice-ai .own-ai-eye', { opacity: [0.2, 1], duration: 600, delay: 1900 });
    },
  },
  {
    at: 79000,
    beat: 'Hers, not an agent',
    text: 'Her personal AI is not another agent asking for things. It holds her key and it knows her terms — it is the side that answers, moved onto a machine of hers.',
    end: { '#alice-ai-key': { opacity: 1 } },
    play() {
      animate('#alice-ai-key', { opacity: [0, 1], y: [-8, 0], duration: 700, ease: 'outBack' });
      animate('#as-shield', { stroke: [C.rest, C.own, C.rest], duration: 1600, delay: 800 });
    },
  },
  {
    at: 85000,
    beat: 'So she is not woken',
    text: 'For the tiers she has already stood behind, her AI answers and the door opens. She is not at her desk, and she does not need to be — the decision was hers, made earlier.',
    end: { '#alice': { x: OFFSTAGE_L }, '#agent': { x: AGENT_MARK, opacity: 0 },
           '#vault-spokes': { rotate: 740 } },
    play() {
      animate('#alice', { x: [HOME, OFFSTAGE_L], duration: 1500, ease: 'inSine' });
      animate('#agent', {
        opacity: [0, 1], x: [OFFSTAGE_L - 90, AGENT_MARK], duration: 1400, ease: 'outSine',
      });
      // Everything that happens on her side is two eyes blinking.
      animate('#alice-ai .own-ai-eye', { opacity: [1, 0.25, 1], duration: 520, loop: 2, delay: 1500 });
      animate('#key', {
        opacity: [0, 1], x: [OWN_MARK, VAULT_CENTRE - 60], y: [GROUND - 150, GROUND - 150],
        rotate: [0, 380], duration: 1500, delay: 2500, ease: 'outQuad',
      });
      animate('#vault-spokes', { rotate: [380, 740], duration: 1000, delay: 3600 });
      animate('#vault-yes', { opacity: [0, 1], scale: [0.6, 1], duration: 500, delay: 3800, ease: 'outBack' });
      animate('#key', { opacity: [1, 0], duration: 400, delay: 4200 });
      animate('#vault-yes', { opacity: [1, 0], duration: 400, delay: 5000 });
      animate('#agent', { opacity: [1, 0], duration: 400, delay: 5000 });
    },
  },
  {
    at: 91000,
    beat: 'And it still wakes her',
    text: 'For a trade she has not stood behind, it refuses and asks her. An agent that cannot reach its person must not answer for it — that is the hard part.',
    end: { '#alice-ai': { opacity: 0 }, '#alice-ai-key': { opacity: 0 },
           '#alice': { x: OFFSTAGE_L }, '#phone-screen': { fill: C.sunken } },
    play() {
      animate('#alice-ai .own-ai-eye', { fill: [C.own, C.pending], duration: 500, delay: 400 });
      animate('#phone-screen', { fill: [C.sunken, C.pending], duration: 500, delay: 900 });
      animate('#buzz', { opacity: [0, 1, 0, 1, 0], duration: 1600, delay: 1000 });
      animate('#alice', { x: [OFFSTAGE_L, PHONE_MARK], duration: 1600, delay: 1400, ease: 'outSine' });
      animate('#alice-arm-l', { rotate: [0, -32, 0], duration: 700, delay: 3000 });
      animate('#phone-screen', { fill: [C.pending, C.granted], duration: 400, delay: 3600 });
      animate('#alice-ai .own-ai-eye', { fill: [C.pending, C.own], duration: 400, delay: 3700 });
      animate('#alice', { x: [PHONE_MARK, OFFSTAGE_L], duration: 1600, delay: 4200, ease: 'inSine' });
      animate(['#alice-ai', '#alice-ai-key'], { opacity: [1, 0], duration: 700, delay: 4600 });
    },
  },
  {
    at: 97000,
    beat: 'The architecture',
    text: 'That is the protocol. This is the machine it runs on — and the four beats are the same four beats.',
    end: {
      '#story': { opacity: 0 }, '#arch': { opacity: 1 },
      '#ns-bob': { opacity: 1 }, '#ns-edge': { opacity: 1 },
      '#ns-meridian': { opacity: 1 }, '#ns-alice': { opacity: 1 },
    },
    play() {
      // The story's set strikes; the machine fades up in its place.
      animate('#story', { opacity: [1, 0], duration: 600 });
      animate('#arch', { opacity: [0, 1], duration: 700, delay: 400 });
      animate(['#ns-bob', '#ns-edge', '#ns-meridian', '#ns-alice'], {
        opacity: [0, 1], duration: 600, delay: (_, i) => 700 + i * 260,
      });
    },
  },
  {
    at: 103000,
    beat: 'The parties',
    text: 'Each party is its own boundary. Bob’s firm, the brokerage that holds the assets, and Alice — who owns them and is not either of the others.',
    end: {
      '#arch-agent': { opacity: 1 }, '#arch-operator': { opacity: 1 },
      '#arch-edge': { opacity: 1 }, '#arch-agw': { opacity: 1 },
      '#arch-pep': { opacity: 1 }, '#arch-vault': { opacity: 1 },
      '#arch-as': { opacity: 1 }, '#arch-db': { opacity: 1 },
      '#arch-keycloak': { opacity: 1 }, '#arch-portal': { opacity: 1 },
    },
    play() {
      const nodes = ['#arch-agent', '#arch-operator', '#arch-edge', '#arch-agw',
                     '#arch-pep', '#arch-vault', '#arch-as', '#arch-db',
                     '#arch-keycloak', '#arch-portal'];
      animate(nodes, {
        opacity: [0, 1], duration: 420, delay: (_, i) => i * 170, ease: 'outQuad',
      });
    },
  },
  {
    at: 109400,
    beat: 'The mesh',
    text: 'Every connection between them is mutually authenticated, and every box has a cryptographic name rather than an address.',
    end: { '#arch-mesh': { opacity: 1 } },
    play() {
      animate('#arch-mesh', { opacity: [0, 1], duration: 700 });
      animate('#arch-mesh .mesh-line', {
        strokeDashoffset: [40, 0], duration: 900, delay: (_, i) => i * 90,
      });
    },
  },
  {
    at: 114600,
    beat: 'Beat 1 · challenge',
    text: 'The agent arrives at the front door like anyone else, and the enforcement point in front of the vault refuses it — with a ticket.',
    end: { '#beat-1': { opacity: 1 } },
    play() {
      animate('#beat-1', { opacity: [0, 1], duration: 500 });
      animate('#beat-1 .flow', { strokeDashoffset: [180, 0], duration: 900, ease: 'outQuad' });
      animate('#arch-pep .shield-sm', {
        stroke: [C.rest, C.pending, C.rest], duration: 1400, delay: 700,
      });
    },
  },
  {
    at: 119800,
    beat: 'Beats 2 and 3',
    text: 'The ticket takes it past the resource server entirely, to Alice’s own authorization server — three of them, agreeing through one database.',
    end: { '#beat-2': { opacity: 1 }, '#arch-scale': { opacity: 1 } },
    play() {
      animate('#beat-2', { opacity: [0, 1], duration: 500 });
      animate('#beat-2 .flow', { strokeDashoffset: [420, 0], duration: 1300, ease: 'outQuad' });
      animate('#arch-as', { scale: [1, 1.03, 1], duration: 900, delay: 1100 });
      animate('#arch-scale', {
        opacity: [0, 1], y: [-8, 0], duration: 600, delay: 1600, ease: 'outBack',
      });
    },
  },
  {
    at: 125600,
    beat: 'Beat 4 · grant',
    text: 'What comes back is scoped to what was agreed, and the enforcement point spends it once. A second attempt with the same grant is refused.',
    end: { '#beat-4': { opacity: 1 } },
    play() {
      animate('#beat-4', { opacity: [0, 1], duration: 500 });
      animate('#beat-4 .flow', { strokeDashoffset: [320, 0], duration: 1100, ease: 'outQuad' });
      animate('#arch-vault .row-own', {
        fill: ['rgba(91, 140, 255, 0.35)', 'rgba(46, 208, 121, 0.45)'],
        duration: 700, delay: 900,
      });
      animate('#arch-pep .shield-sm', {
        stroke: [C.rest, C.granted, C.rest], duration: 1400, delay: 900,
      });
    },
  },
  {
    at: 131200,
    beat: 'The boundary',
    text: 'And there is no shortcut. Bob’s side cannot reach Alice’s at all — not because nobody wrote the address down, but because the mesh refuses it.',
    end: { '#arch-denied': { opacity: 1 } },
    play() {
      animate('#arch-denied', { opacity: [0, 1], duration: 600 });
      animate('#arch-denied .flow--deny', { strokeDashoffset: [520, 0], duration: 900 });
      animate('#arch-denied g', {
        scale: [0.5, 1], duration: 600, delay: 700, ease: 'outBack',
      });
    },
  },
  {
    at: 137000,
    text: '',
    // Strike the machine behind the curtain, exactly as act one does, so the
    // loop opens on the first frame rather than cutting to it.
    end: {
      '#alice': { x: HOME, opacity: 1 }, '#bob': { opacity: 0, x: OFFSTAGE_L },
      '#agent': { opacity: 0, x: OFFSTAGE_L - 90 },
      '#ticket': { x: VAULT_MARK, opacity: 0 },
      '#laptop-lid': { rotate: 0 }, '#place-nightstand': { opacity: 0 },
      '#vault-spokes': { rotate: 0 },
      '#alice-row': { opacity: 0.25 }, '#alice-row .own-row': { stroke: C.edge },
      '#arch': { opacity: 0 }, '#story': { opacity: 1 },
    },
    play() {
      animate('#titlecard', { opacity: [0, 1], duration: 900 });
      animate('#arch', { opacity: [1, 0], duration: 500, delay: 1200 });
      animate('#story', { opacity: [0, 1], duration: 500, delay: 1700 });
      animate('#alice', { opacity: [0, 1], x: [OFFSTAGE_L, HOME], duration: 10, delay: 1800 });
      animate(['#agent', '#bob'], { opacity: [0.16, 0], duration: 400, delay: 1800 });
      animate('#laptop-lid', { rotate: [82, 0], duration: 10, delay: 1800 });
      animate('#place-nightstand', { opacity: [1, 0], duration: 400, delay: 1800 });
      animate('#vault-spokes', { rotate: [380, 0], duration: 10, delay: 1800 });
      animate('#alice-row', { opacity: [1, 0.25], duration: 400, delay: 1800 });
      animate('#alice-row .own-row', { stroke: [C.rest, C.edge], duration: 400, delay: 1800 });
      animate('#titlecard', { opacity: [1, 0], duration: 900, delay: 3400 });
    },
  },
];

const TOTAL = 143000;

/* ---- the machine --------------------------------------------------------- */

export function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Attach the story to a rendered stage.
 *
 * Every lookup is scoped to `root` rather than the document: React owns this
 * markup, and a stray global selector would be a second owner.
 *
 * @param {HTMLElement} root      the element containing the stage and controls
 * @param {(i:number)=>void} onScene  called when the visible scene changes
 * @returns {() => void} teardown
 */
export function mount(root, onScene) {
  const $ = (sel) => root.querySelector(sel);

  readTheme();

  function apply(state) {
    for (const [sel, props] of Object.entries(state)) {
      const targets = root.querySelectorAll(sel);
      if (targets.length) utils.set(targets, painted(props));
    }
  }

  /* The stage as it stands at the start of scene `i`: the base, plus what
   * every earlier scene left behind. Deriving it rather than storing it is
   * what makes scrubbing exact — there is no snapshot to drift out of date. */
  function stateAt(i) {
    const out = structuredClone(BASE);
    for (let n = 0; n < i; n++) {
      for (const [sel, props] of Object.entries(SCENES[n].end)) {
        out[sel] = { ...(out[sel] || {}), ...props };
      }
    }
    return out;
  }

  if (prefersReducedMotion()) {
    /* Nothing moves. The stage holds one readable frame — everyone present,
     * mid-story — and the caption list carries the whole explanation. It
     * still has to be repainted when the theme changes, or the one frame the
     * reader gets keeps the colours of the theme they left. */
    const still = () => {
      readTheme();
      apply(stateAt(5));
      apply({ "#agent": { x: AGENT_MARK }, "#alice": { x: HOME, opacity: 1 } });
    };
    still();
    const stillMedia = window.matchMedia("(prefers-color-scheme: light)");
    window.addEventListener("u4a:themechange", still);
    stillMedia.addEventListener("change", still);
    return () => {
      window.removeEventListener("u4a:themechange", still);
      stillMedia.removeEventListener("change", still);
    };
  }

  const scrub = $(".stage-scrub");
  const toggle = $(".stage-toggle");
  const replay = $(".stage-replay");

  let current = -1;
  let clock = 0;        // ms into the story
  let last = null;      // rAF timestamp of the previous frame
  let playing = true;
  let dragging = false;
  let raf = null;
  let alive = true;

  function showScene(i) {
    current = i;
    apply(stateAt(i));
    SCENES[i].play();
    if (onScene) onScene(i);
  }

  function sceneAt(ms) {
    let i = 0;
    for (let n = 0; n < SCENES.length; n++) if (ms >= SCENES[n].at) i = n;
    return i;
  }

  function frame(now) {
    if (!alive) return;
    raf = requestAnimationFrame(frame);
    if (last === null) last = now;
    const dt = now - last;
    last = now;
    if (!playing || dragging) return;

    clock += dt;
    if (clock >= TOTAL) clock -= TOTAL;    // and round again
    const want = sceneAt(clock);
    if (want !== current) showScene(want);
    if (scrub) scrub.value = Math.round((clock / TOTAL) * 1000);
  }

  function setPlaying(on) {
    playing = on;
    if (!toggle) return;
    toggle.textContent = on ? "Pause" : "Play";
    toggle.setAttribute("aria-label", on ? "Pause" : "Play");
  }

  const onToggle = () => setPlaying(!playing);
  const onReplay = () => {
    clock = 0;
    showScene(0);
    setPlaying(true);
  };
  const onDown = () => {
    dragging = true;
    setPlaying(false);
  };
  const onUp = () => {
    dragging = false;
  };
  /* Scrubbing lands on a scene, which is the unit a presenter actually wants
   * to hold — and, conveniently, the unit whose state is exactly derivable. */
  const onInput = () => {
    clock = (scrub.value / 1000) * TOTAL;
    const want = sceneAt(clock);
    if (want !== current) showScene(want);
  };
  /* A presenter's convenience: space holds a beat without hunting for the
     button. Ignored while a control has focus, so the buttons still work. */
  const onKey = (e) => {
    if (e.code === "Space" && !["BUTTON", "INPUT", "TEXTAREA"].includes(e.target.tagName)) {
      e.preventDefault();
      setPlaying(!playing);
    }
  };

  if (toggle) toggle.addEventListener("click", onToggle);
  if (replay) replay.addEventListener("click", onReplay);
  if (scrub) {
    scrub.addEventListener("pointerdown", onDown);
    scrub.addEventListener("pointerup", onUp);
    scrub.addEventListener("input", onInput);
  }
  document.addEventListener("keydown", onKey);

  showScene(0);
  raf = requestAnimationFrame(frame);

  /* A theme change repaints the stage. Re-reading the properties is not
     enough on its own: the colours already written onto elements by earlier
     scenes came from the old palette, so the current scene is replayed, which
     re-applies every accumulated state through `paint`. */
  function onTheme() {
    readTheme();
    if (current >= 0) showScene(current);
  }
  const media = window.matchMedia("(prefers-color-scheme: light)");
  window.addEventListener("u4a:themechange", onTheme);
  media.addEventListener("change", onTheme);

  return () => {
    alive = false;
    if (raf) cancelAnimationFrame(raf);
    if (toggle) toggle.removeEventListener("click", onToggle);
    if (replay) replay.removeEventListener("click", onReplay);
    if (scrub) {
      scrub.removeEventListener("pointerdown", onDown);
      scrub.removeEventListener("pointerup", onUp);
      scrub.removeEventListener("input", onInput);
    }
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("u4a:themechange", onTheme);
    media.removeEventListener("change", onTheme);
  };
}

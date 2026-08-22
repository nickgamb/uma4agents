// The documentation, as an ordered structure.
//
// Authored, never derived from the filesystem. Reading order is an editorial
// decision — a concept has to come before the guide that assumes it — and
// filenames cannot express that. The link checker walks this file against the
// pages that actually built, so a page added without a home here fails the
// build rather than becoming unreachable.
//
// Three sections, deliberately. Overview is long because everything
// explanatory belongs together: what the shape is, how each piece works, and
// how it sits next to the adjacent standards. Splitting those into separate
// tabs made the reader guess which one held the answer.
//
// `to` is the page's URL, and the markdown lives at the matching path under
// src/pages/ — so /docs/overview/four-beats/ is
// src/pages/docs/overview/four-beats.md.
//
// CommonJS on purpose, for the same reason src/style/theme.js is: this file is
// read both by webpack for the app and by plain Node in scripts/, and the build
// pins Node 20, which cannot `require` an ES module. Reading order has to be
// the same list for the sidebar, the search index and the link checker — two
// copies would drift.

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "guides", label: "Guides" },
  { id: "reference", label: "Reference" },
];

const nav = {
  overview: [
    {
      group: "Start here",
      pages: [
        { title: "Overview", to: "/docs/overview/" },
        { title: "Why the owner decides", to: "/docs/overview/why/" },
        { title: "Architecture", to: "/docs/overview/architecture/" },
        { title: "Concepts", to: "/docs/overview/concepts/" },
        { title: "Standards this composes", to: "/docs/overview/standards/" },
      ],
    },
    {
      group: "The grant",
      pages: [
        { title: "The four beats", to: "/docs/overview/four-beats/" },
        { title: "The three parties", to: "/docs/overview/parties/" },
        { title: "Terms as first-class", to: "/docs/overview/terms/" },
        { title: "The two intents", to: "/docs/overview/two-intents/" },
        { title: "Her own agent", to: "/docs/overview/first-party/" },
      ],
    },
    {
      group: "What holds it together",
      pages: [
        { title: "Identity is not authorization", to: "/docs/overview/identity/" },
        { title: "Identity stays where it is", to: "/docs/overview/flow/" },
        { title: "Discovery, public and protected", to: "/docs/overview/discovery/" },
        { title: "Proof-of-possession", to: "/docs/overview/proof-of-possession/" },
        { title: "Single-use means indivisible", to: "/docs/overview/single-use/" },
        { title: "Revocation and the ledger", to: "/docs/overview/revocation/" },
        { title: "Agent assurance", to: "/docs/overview/assurance/" },
        { title: "The owner's attention", to: "/docs/overview/attention/" },
        { title: "Many owners, one resource server", to: "/docs/overview/multi-owner/" },
      ],
    },
    {
      group: "How it compares",
      pages: [
        { title: "UMA 2.0", to: "/docs/overview/compare-uma/" },
        { title: "OAuth 2.0 and GNAP", to: "/docs/overview/compare-oauth-gnap/" },
        { title: "Policy engines", to: "/docs/overview/compare-policy-engines/" },
        { title: "Agent identity", to: "/docs/overview/compare-agent-identity/" },
      ],
    },
    {
      group: "Resources",
      pages: [
        { title: "Glossary", to: "/docs/overview/glossary/" },
        { title: "FAQ", to: "/docs/overview/faq/" },
      ],
    },
  ],

  guides: [
    {
      group: "Getting started",
      pages: [
        { title: "The roles you must fill", to: "/docs/guides/roles/" },
        { title: "Run the lab", to: "/docs/guides/run-the-lab/" },
      ],
    },
    {
      group: "Build the grant",
      pages: [
        { title: "Choose an enforcement point", to: "/docs/guides/enforcement-point/" },
        { title: "Issue the challenge", to: "/docs/guides/challenge/" },
        { title: "Dictate terms, take an agreement", to: "/docs/guides/terms/" },
        { title: "Mint an operation-bound grant", to: "/docs/guides/grant/" },
      ],
    },
    {
      group: "Make it hold up",
      pages: [
        { title: "Make single-use indivisible", to: "/docs/guides/indivisible/" },
        { title: "Wire the owner's approval path", to: "/docs/guides/approval/" },
        { title: "Let the owner write her own policy", to: "/docs/guides/owner-policy/" },
        { title: "Put the authority on her device", to: "/docs/guides/personal-authority/" },
        { title: "Deploy it at scale", to: "/docs/guides/at-scale/" },
      ],
    },
  ],

  reference: [
    {
      group: "The wire",
      pages: [
        { title: "Wire contract", to: "/docs/reference/wire-contract/" },
        { title: "Endpoints", to: "/docs/reference/endpoints/" },
        { title: "Events", to: "/docs/reference/events/" },
        { title: "MCP binding", to: "/docs/reference/mcp-binding/" },
      ],
    },
    {
      group: "Running it",
      pages: [
        { title: "Configuration", to: "/docs/reference/configuration/" },
      ],
    },
    {
      group: "For spec authors",
      pages: [
        { title: "Deviations from UMA 2.0", to: "/docs/reference/deviations/" },
        { title: "Findings", to: "/docs/reference/findings/" },
      ],
    },
  ],
};

/** Every page, flat and in reading order. */
const allPages = () =>
  tabs.flatMap((t) =>
    (nav[t.id] || []).flatMap((g) =>
      g.pages.map((p) => ({ ...p, tab: t.id, tabLabel: t.label, group: g.group }))
    )
  );

/** Which tab a URL belongs to, for highlighting the tab bar. */
const tabForPath = (pathname) => {
  const hit = allPages().find((p) => p.to === pathname);
  return hit ? hit.tab : (pathname.split("/")[2] || "overview");
};

/** The page before and after this one, in reading order, for the footer. */
const neighbours = (pathname) => {
  const flat = allPages();
  const i = flat.findIndex((p) => p.to === pathname);
  return i === -1
    ? { prev: null, next: null }
    : { prev: flat[i - 1] || null, next: flat[i + 1] || null };
};

module.exports = { tabs, nav, allPages, tabForPath, neighbours, default: nav };

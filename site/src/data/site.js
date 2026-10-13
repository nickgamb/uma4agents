// Shared site chrome for u4a.ai.

export const repo = "https://github.com/nickgamb/uma4agents";

// Each person, and the company they run. The company sits under the person
// rather than in a separate list: this block credits the two people who built
// U4A, and where they work is part of who they are — not a sponsor row.
export const people = [
  {
    name: "Nick Gamb",
    linkedin: "https://www.linkedin.com/in/nickgamb/",
    org: {
      name: "MindGarden",
      url: "https://mindgardenai.com",
      icon: "/img/orgs/mindgarden.png",
    },
  },
  {
    name: "Eve Maler",
    linkedin: "https://www.linkedin.com/in/evemaler/",
    org: {
      name: "Venn Factory",
      url: "https://www.vennfactory.com",
      icon: "/img/orgs/vennfactory.svg",
    },
  },
];

export const navLinks = [
  { label: "Docs", to: "/docs/overview/" },
  { label: "Changelog", to: "/changelog/" },
  { label: "Blog", to: "/blog/" },
  { label: "Contact", to: "/contact/" },
];

// The site's call to action. Two doors rather than one: the lab can now be
// run in a browser without installing anything, and that is a stronger first
// step than reading source — but the source is what makes the claim checkable,
// so it stays one click away rather than behind a scroll.
export const ctaLabel = "Try the lab";

export const codespace =
  "https://codespaces.new/nickgamb/uma4agents?devcontainer_path=.devcontainer%2Fdevcontainer.json";

export const ctaActions = [
  {
    label: "Run it in Codespaces",
    hint: "The Kubernetes lab, in your browser",
    href: codespace,
  },
  {
    label: "View on GitHub",
    hint: "Clone it, read it, check the claims",
    href: repo,
  },
];

export const tagline = "She isn’t online. Her policy is.";

export const footerBlurb =
  "A working proof-of-concept carrying User-Managed Access into the agent era: the owner sets policy once, and other people’s agents negotiate against it while she is offline.";

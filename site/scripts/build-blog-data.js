#!/usr/bin/env node
/**
 * Reads the blog and docs Markdown and writes the indexes that are not pages:
 *
 *   netlify/functions/blog-data.json   what the MCP server answers from
 *   netlify/functions/docs-data.json   the same, for the documentation
 *   netlify/functions/changelog-data.json  the same, for the changelog
 *   static/search-index.json           what ⌘K filters, client-side
 *   static/llms.txt                    the guided index for language models
 *
 * All generated rather than maintained, because any of them going stale is
 * invisible — a missing page does not break a build, it just quietly stops
 * being findable.
 *
 * Runs from `prebuild` / `predevelop`.
 */
const fs = require("fs");
const path = require("path");
const siteMetadata = require("../site-meta");
const { allPages } = require("../src/data/docs-nav");
const { scriptFor, titleFor } = require("../src/data/figure-scripts");

const root = path.join(__dirname, "..");
const BLOG_DIR = path.join(root, "src", "pages", "blog");
const DOCS_DIR = path.join(root, "src", "pages", "docs");
const DATA_OUT = path.join(root, "netlify", "functions", "blog-data.json");
const DOCS_OUT = path.join(root, "netlify", "functions", "docs-data.json");
const CHANGELOG_DIR = path.join(root, "src", "pages", "changelog");
const CHANGELOG_OUT = path.join(root, "netlify", "functions", "changelog-data.json");
const SEARCH_OUT = path.join(root, "static", "search-index.json");
const LLMS_OUT = path.join(root, "static", "llms.txt");
const SITE = siteMetadata.siteUrl;

/**
 * A deliberately small frontmatter reader.
 *
 * It handles exactly the shapes these posts use — `key: value` and a block
 * list of `- item` — rather than pulling in a YAML parser for two files.
 */
function parseFrontmatter(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return { frontmatter: {}, body: content };

  const frontmatter = {};
  let currentKey = null;
  let listItems = [];

  for (const line of match[1].split("\n")) {
    const listMatch = line.match(/^\s+-\s+(.+)/);
    if (listMatch && currentKey) {
      listItems.push(listMatch[1].replace(/^["']|["']$/g, ""));
      continue;
    }
    if (currentKey && listItems.length > 0) {
      frontmatter[currentKey] = listItems;
      listItems = [];
      currentKey = null;
    }
    const kv = line.match(/^(\w+):\s*(.*)/);
    if (kv) {
      const key = kv[1];
      let value = kv[2].trim().replace(/^["']|["']$/g, "");
      if (value === "true") value = true;
      else if (value === "false") value = false;
      else if (value === "") {
        currentKey = key;
        listItems = [];
        continue;
      }
      frontmatter[key] = value;
      currentKey = null;
    }
  }
  if (currentKey && listItems.length > 0) frontmatter[currentKey] = listItems;

  return { frontmatter, body: match[2].trim() };
}

const posts = fs
  .readdirSync(BLOG_DIR)
  .filter((f) => f.endsWith(".md"))
  .map((filename) => {
    const { frontmatter, body } = parseFrontmatter(
      fs.readFileSync(path.join(BLOG_DIR, filename), "utf-8")
    );
    const slug = filename.replace(/\.md$/, "");
    return {
      slug,
      url: `/blog/${slug}/`,
      markdown: `/blog/${slug}.md`,
      title: frontmatter.title || slug,
      date: frontmatter.date || null,
      author: frontmatter.author || null,
      description: frontmatter.description || null,
      category: frontmatter.category || null,
      tags: frontmatter.tags || [],
      featuredpost: frontmatter.featuredpost || false,
      featuredimage: frontmatter.featuredimage || null,
      body,
    };
  })
  .sort((a, b) => (a.date && b.date ? new Date(b.date) - new Date(a.date) : 0));

fs.mkdirSync(path.dirname(DATA_OUT), { recursive: true });
fs.writeFileSync(DATA_OUT, JSON.stringify(posts, null, 2));

// --- the documentation ---------------------------------------------------
// Walked in the reading order docs-nav.js declares rather than in filesystem
// order, so an agent listing the docs gets them in the sequence a person would
// read them. A page in the nav with no file is a build failure here, which is
// the cheapest place to catch it.
const docs = allPages().map((entry) => {
  const rel = entry.to.replace(/^\/docs\//, "").replace(/\/$/, "");
  const candidates = [
    path.join(DOCS_DIR, `${rel}.md`),
    path.join(DOCS_DIR, rel, "index.md"),
  ];
  const file = candidates.find((c) => fs.existsSync(c));
  if (!file) {
    throw new Error(
      `docs-nav.js lists ${entry.to} but neither ${path.relative(root, candidates[0])} ` +
        `nor ${path.relative(root, candidates[1])} exists`
    );
  }

  const { frontmatter, body } = parseFrontmatter(fs.readFileSync(file, "utf-8"));

  // An animated figure's captions are part of the page's explanation, so they
  // travel with the body rather than being left behind in a React component
  // that only a browser can run.
  const steps = scriptFor(frontmatter.diagram);
  const figure = steps.length
    ? `\n\n## Figure: ${titleFor(frontmatter.diagram)}\n\n` +
      steps.map((s, i) => `${i + 1}. ${s}`).join("\n")
    : "";

  return {
    slug: rel,
    url: entry.to,
    markdown: `${entry.to.replace(/\/$/, "")}.md`,
    title: frontmatter.title || entry.title,
    description: frontmatter.description || null,
    section: entry.tabLabel,
    group: entry.group,
    figure: steps.length ? { title: titleFor(frontmatter.diagram), steps } : null,
    headings: (body.match(/^##+ .+$/gm) || []).map((h) =>
      h.replace(/^#+\s*/, "")
    ),
    body: body + figure,
  };
});

fs.writeFileSync(DOCS_OUT, JSON.stringify(docs, null, 2));

// --- the changelog -------------------------------------------------------
// One entry per release, split out of the page so an agent can be asked what
// changed on a date without being handed the whole file. The date headings
// are `## `, the version is the paragraph under each, and everything below a
// heading belongs to it — which is the page's own structure rather than a
// second format maintained beside it.
const changelog = fs
  .readdirSync(CHANGELOG_DIR)
  .filter((f) => f.endsWith(".md"))
  .flatMap((file) => {
    const { frontmatter, body } = parseFrontmatter(
      fs.readFileSync(path.join(CHANGELOG_DIR, file), "utf-8")
    );
    const slug = file === "index.md" ? "" : `/${file.replace(/\.md$/, "")}`;
    const url = `/changelog${slug}/`;
    // `## ` is the date and `### ` the release under it, because several
    // land on most days. One record per release, carrying its date.
    return body
      .split(/^## /m)
      .slice(1)
      .flatMap((day) => {
        const [date, ...dayRest] = day.split("\n");
        return dayRest
          .join("\n")
          .split(/^### /m)
          .slice(1)
          .map((chunk) => {
            const [version, ...rest] = chunk.split("\n");
            const text = rest.join("\n").trim();
            return { date: date.trim(), version: version.trim(), text };
          });
      })
      .map(({ date, version, text }) => {
        return {
          date,
          version,
          url,
          page: frontmatter.title || "Changelog",
          // Every line that is a change, without the section headings — the
          // headings say which kind, and the kind travels on the line below.
          changes: (text.match(/^- .+$/gm) || []).map((l) =>
            l.replace(/^- /, "").replace(/\*\*/g, "")
          ),
          body: text,
        };
      });
  });

fs.writeFileSync(CHANGELOG_OUT, JSON.stringify(changelog, null, 2));

// --- the search index ----------------------------------------------------
// Deliberately small: title, where it sits, its headings, and the first
// paragraph. Enough for a name-what-you-want search over a few dozen pages,
// and small enough that shipping the whole thing to the browser is cheaper
// than standing up a search service for it.
const firstParagraph = (body) => {
  const para = body
    .split(/\n\n+/)
    .map((p) => p.trim())
    .find((p) => p && !p.startsWith("#") && !p.startsWith("```") && !p.startsWith("|"));
  return para ? para.replace(/\s+/g, " ").slice(0, 240) : "";
};

const searchIndex = [
  ...docs.map((d) => ({
    title: d.title,
    url: d.url,
    section: d.section,
    group: d.group,
    description: d.description || firstParagraph(d.body),
    // A figure's steps are searchable text. Someone looking for "unsigned
    // replay" should land on the grant guide, and that phrase only exists in
    // the enforcement-order figure.
    headings: d.figure
      ? [...d.headings, d.figure.title, ...d.figure.steps]
      : d.headings,
  })),
  // One row per release rather than one for the page: somebody searching
  // "break-glass" wants the day it landed, and a single Changelog row would
  // match everything and locate nothing.
  ...changelog.map((c) => ({
    title: c.version ? `${c.date} — ${c.version}` : c.date,
    url: c.url,
    section: "Changelog",
    group: c.date.replace(/^\w+ \d+ /, ""),
    description: c.changes[0] || "",
    headings: c.changes,
  })),
  ...posts.map((p) => ({
    title: p.title,
    url: p.url,
    section: "Blog",
    group: p.category || "Posts",
    description: p.description || firstParagraph(p.body),
    headings: (p.body.match(/^##+ .+$/gm) || []).map((h) =>
      h.replace(/^#+\s*/, "")
    ),
  })),
];

fs.mkdirSync(path.dirname(SEARCH_OUT), { recursive: true });
fs.writeFileSync(SEARCH_OUT, JSON.stringify(searchIndex));

// --- llms.txt (https://llmstxt.org) --------------------------------------
const llms = [
  `# ${siteMetadata.title}`,
  "",
  `> ${siteMetadata.description}`,
  "",
  "A working proof-of-concept, with Eve Maler, carrying User-Managed Access",
  "(UMA) 2.0 into the agent era: the resource owner sets policy once, and other",
  "people's AI agents negotiate access against it while she is offline. The lab",
  "runs locally with one command and also deploys to Kubernetes.",
  "",
  "Every page below is available as plain Markdown by appending `.md` to its",
  "URL. The site also speaks MCP at " + `${SITE}/mcp` + " with four tools —",
  "`listDocs`, `getDoc`, `listBlogs` and `getBlog` — if you would rather read",
  "it that way.",
  "",
  "## Documentation",
  "",
  "Concept pages explain one idea; guides walk a procedure end to end; the",
  "reference is the wire contract, the endpoints and the deviations from",
  "UMA 2.0. Listed in reading order.",
  "",
  ...docs.map(
    (d) =>
      `- [${d.section} · ${d.title}](${SITE}${d.markdown}): ${d.description || ""}`.trimEnd()
  ),
  "",
  "## Changelog",
  "",
  "Every release, newest first. One entry per merged change; several land on",
  "most days.",
  "",
  ...changelog
    .slice(0, 12)
    .map(
      (c) =>
        `- [${c.date}${c.version ? ` · ${c.version}` : ""}](${SITE}/changelog.md): ` +
        `${c.changes[0] || ""}`.trimEnd()
    ),
  `- [The full changelog](${SITE}/changelog.md): every release since the first.`,
  "",
  "## Posts",
  "",
  ...posts.map(
    (p) => `- [${p.title}](${SITE}${p.markdown}): ${p.description || ""}`.trimEnd()
  ),
  "",
  "## Pages",
  "",
  `- [Home](${SITE}/): The four-beat grant as an animated walkthrough — challenge, terms, commit, grant.`,
  `- [Docs](${SITE}/docs/overview/): Concepts, guides and the wire contract.`,
  `- [Changelog](${SITE}/changelog/): Every release of the reference architecture, newest first.`,
  `- [Blog](${SITE}/blog/): Working notes on carrying UMA into the agent era.`,
  `- [Contact](${SITE}/contact/): Use cases, problems and ideas are what shape where this goes next.`,
  "",
  "## Source",
  "",
  "- [Repository](https://github.com/nickgamb/uma4agents): Apache-2.0. The lab, the reference architecture, and the specs it profiles.",
  "- [FINDINGS.md](https://github.com/nickgamb/uma4agents/blob/main/FINDINGS.md): Recommendations to the spec authors, each backed by running code.",
  "- [docs/PROTOCOL.md](https://github.com/nickgamb/uma4agents/blob/main/docs/PROTOCOL.md): The wire contract, including where this profile deviates from UMA 2.0 and why.",
  "- [docs/KUBERNETES.md](https://github.com/nickgamb/uma4agents/blob/main/docs/KUBERNETES.md): The deployed reference architecture and a fifteen-minute demo guide.",
  "",
].join("\n");

fs.writeFileSync(LLMS_OUT, llms);

const rel = (p) => path.relative(process.cwd(), p);
console.log(
  `indexes: ${posts.length} posts, ${docs.length} doc pages\n` +
    [DATA_OUT, DOCS_OUT, SEARCH_OUT, LLMS_OUT].map((p) => `  ${rel(p)}`).join("\n")
);

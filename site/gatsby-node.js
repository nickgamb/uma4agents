const path = require("path");
const { createFilePath } = require("gatsby-source-filesystem");

const slugify = require("./src/utils/slugify");

exports.createSchemaCustomization = ({ actions }) => {
  actions.createTypes(`
    type DocNext {
      title: String
      to: String
      blurb: String
    }
    type MarkdownRemarkFrontmatter {
      templateKey: String
      title: String
      # Documentation only: the cards a page ends on. Typed explicitly because
      # inference cannot see the shape until some page happens to use it, and
      # a docs page without the field would otherwise break the query for
      # every page that has it.
      next: [DocNext]
      # Documentation only: a demo video, loaded on click rather than on load.
      video: String
      videoTitle: String
      videoPoster: String
      date: Date @dateformat
      author: String
      description: String
      featuredpost: Boolean
      featuredimage: String
      category: String
      tags: [String]
    }
    type MarkdownRemark implements Node {
      frontmatter: MarkdownRemarkFrontmatter
    }
  `);
};

exports.createPages = async ({ actions, graphql }) => {
  const result = await graphql(`
    {
      allMarkdownRemark(limit: 1000) {
        edges {
          node {
            id
            fields {
              slug
            }
            frontmatter {
              templateKey
              tags
              author
            }
          }
        }
      }
    }
  `);
  if (result.errors) throw result.errors;

  const posts = result.data.allMarkdownRemark.edges;

  posts.forEach(({ node }) => {
    const { templateKey } = node.frontmatter;
    if (!templateKey) return;
    actions.createPage({
      path: node.fields.slug,
      component: path.resolve(`src/templates/${templateKey}.js`),
      context: { id: node.id },
    });
  });

  // A page per tag. The query filters on the tag's own text, so the slug is
  // only ever the URL — which is why the templates and this share slugify()
  // rather than each having their own idea of what a tag looks like.
  const tags = [
    ...new Set(posts.flatMap(({ node }) => node.frontmatter.tags || [])),
  ];
  tags.forEach((tag) => {
    actions.createPage({
      path: `/tags/${slugify(tag)}/`,
      component: path.resolve("src/templates/tags.js"),
      context: { tag },
    });
  });

  // And a page per author, which is where the bio lives.
  const authors = [
    ...new Set(posts.map(({ node }) => node.frontmatter.author).filter(Boolean)),
  ];
  authors.forEach((author) => {
    actions.createPage({
      path: `/authors/${slugify(author)}/`,
      component: path.resolve("src/templates/author.js"),
      context: { author },
    });
  });
};

exports.onCreateNode = ({ node, actions, getNode }) => {
  if (node.internal.type === "MarkdownRemark") {
    actions.createNodeField({
      name: "slug",
      node,
      value: createFilePath({ node, getNode }),
    });
  }
};

/**
 * Write public/sitemap.xml from the pages that were actually emitted.
 *
 * The routes are read off the built output — every public/**\/index.html is a
 * page — rather than from `allSitePage`, which comes back empty in this
 * project by the time onPostBuild runs. That is also what made
 * gatsby-plugin-sitemap useless here: it queries for the same thing, gets
 * nothing, and writes a zero-byte sitemap *without failing the build*.
 *
 * Reading the filesystem has the additional virtue of describing what
 * shipped rather than what the build intended to ship.
 */
function writeSitemap({ fs, siteMeta }) {
  const publicDir = path.resolve("public");

  const walk = (dir) =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) return walk(full);
      return entry.name === "index.html" ? [path.dirname(full)] : [];
    });

  const paths = walk(publicDir)
    .map((d) => {
      const rel = path.relative(publicDir, d);
      return rel === "" ? "/" : `/${rel.split(path.sep).join("/")}/`;
    })
    .filter((p) => !p.startsWith("/404"))
    .sort();

  if (paths.length === 0) {
    throw new Error("sitemap: no pages found — refusing to write an empty one");
  }

  const urls = paths
    .map((p) => {
      // The documentation is the reference material this site exists to
      // publish, so it ranks with the posts rather than below them. Its
      // section entry points sit one step higher again, because those are the
      // pages a search result should land on when the query is about the
      // profile as a whole rather than one mechanism inside it.
      const priority =
        p === "/"
          ? "1.0"
          : ["/docs/overview/", "/docs/guides/roles/", "/docs/reference/wire-contract/"].includes(p)
          ? "0.9"
          : p.startsWith("/blog/") || p.startsWith("/docs/") || p.startsWith("/changelog")
          ? "0.8"
          : "0.6";
      // Most of this site changes when something is rewritten. The changelog
      // changes when anything ships, which is several times a day, and a
      // crawler told "weekly" will keep serving a stale one.
      const changefreq = p.startsWith("/changelog") ? "daily" : "weekly";
      return [
        "  <url>",
        `    <loc>${siteMeta.siteUrl}${p}</loc>`,
        `    <changefreq>${changefreq}</changefreq>`,
        `    <priority>${priority}</priority>`,
        "  </url>",
      ].join("\n");
    })
    .join("\n");

  fs.writeFileSync(
    path.resolve("public/sitemap.xml"),
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
      `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`
  );
  console.info(`Wrote sitemap.xml with ${paths.length} URLs`);
}

/**
 * Publish a plain-Markdown copy of every page under a section, beside its
 * HTML page — e.g. /docs/overview/why.md next to /docs/overview/why/.
 *
 * The URL is what PageActions asks for: the page path with its trailing slash
 * dropped and `.md` appended. So a section index at src/pages/docs/overview/
 * index.md lands at /docs/overview.md — one level up from where the source
 * file sits — because /docs/overview/ is the page it belongs to. The
 * changelog's index.md lands at /changelog.md for the same reason.
 *
 * Parameterised by section rather than copied per section: the twins are what
 * the "Copy page" action and every language model read, and a section whose
 * twins were written by a second copy of this is a section whose twins go
 * stale on their own schedule.
 */
function writeMarkdownTwins({ fs, siteMeta, section }) {
  const srcRoot = path.resolve(`src/pages/${section}`);
  if (!fs.existsSync(srcRoot)) return 0;

  const { scriptFor, titleFor } = require("./src/data/figure-scripts");

  const walk = (dir) =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) return walk(full);
      return entry.name.endsWith(".md") ? [full] : [];
    });

  let written = 0;

  for (const file of walk(srcRoot)) {
    const raw = fs.readFileSync(file, "utf8");
    const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    const body = match ? match[2].trim() : raw.trim();

    const field = (key) => {
      const m = match && match[1].match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
      return m ? m[1].trim().replace(/^["']|["']$/g, "") : "";
    };

    const rel = path
      .relative(srcRoot, file)
      .split(path.sep)
      .join("/")
      .replace(/\.md$/, "")
      .replace(/(^|\/)index$/, "");
    const url = `/${section}/${rel}/`.replace(/\/+$/, "/");
    const out = path.resolve(
      rel === ""
        ? `public/${section}.md`
        : `public/${section}/${rel.replace(/\/$/, "")}.md`
    );

    const header = [
      `# ${field("title")}`,
      "",
      `Source: ${siteMeta.siteUrl}${url}`,
      "",
      "---",
      "",
    ].join("\n");

    // A page with an animated figure carries part of its explanation in that
    // figure's captions. They are real prose, so the plain-Markdown copy has
    // to include them — otherwise the version an agent reads is missing
    // whatever the page chose to say in pictures.
    const steps = scriptFor(field("diagram"));
    const figure = steps.length
      ? [
          "",
          `## Figure: ${titleFor(field("diagram"))}`,
          "",
          ...steps.map((s, i) => `${i + 1}. ${s}`),
          "",
        ].join("\n")
      : "";

    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, header + body + "\n" + figure);
    written += 1;
  }

  return written;
}

/**
 * Publish a plain-Markdown copy of every post beside its HTML page, e.g.
 * /blog/2026-08-06-let-them-a-developers-guide-to-u4a.md
 *
 * This is what the "View as Markdown" action reads, and it gives language
 * models a clean source to ingest without stripping page chrome — which
 * matters more than usual for a site whose subject is what agents are and
 * are not allowed to do with someone else's material.
 */
exports.onPostBuild = async () => {
  const fs = require("fs");
  const siteMeta = require("./site-meta");
  const srcDir = path.resolve("src/pages/blog");
  const outDir = path.resolve("public/blog");

  // Independent of the Markdown twins below, and written first so that the
  // early return when there are no posts cannot silently skip it.
  writeSitemap({ fs, siteMeta });

  const docs = writeMarkdownTwins({ fs, siteMeta, section: "docs" });
  console.info(`Published ${docs} Markdown copies to /docs/**.md`);
  const changes = writeMarkdownTwins({ fs, siteMeta, section: "changelog" });
  console.info(`Published ${changes} Markdown copies to /changelog**.md`);

  if (!fs.existsSync(srcDir)) return;
  fs.mkdirSync(outDir, { recursive: true });

  const files = fs.readdirSync(srcDir).filter((f) => f.endsWith(".md"));

  for (const file of files) {
    const raw = fs.readFileSync(path.join(srcDir, file), "utf8");
    const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    const body = match ? match[2].trim() : raw.trim();

    const field = (key) => {
      const m = match && match[1].match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
      return m ? m[1].trim().replace(/^["']|["']$/g, "") : "";
    };

    const slug = file.replace(/\.md$/, "");
    const header = [
      `# ${field("title")}`,
      "",
      `Author: ${field("author")}`,
      `Date: ${field("date").slice(0, 10)}`,
      `Source: ${siteMeta.siteUrl}/blog/${slug}/`,
      "",
      "---",
      "",
    ].join("\n");

    fs.writeFileSync(path.join(outDir, `${slug}.md`), header + body + "\n");
  }

  console.info(`Published ${files.length} Markdown copies to /blog/*.md`);
};

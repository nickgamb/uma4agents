import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { z } from "zod";
import { createRequire } from "module";

/**
 * u4a.ai as an MCP server.
 *
 * The site is about agents negotiating for access to things, so it should be
 * readable by one. Pairs of tools: list what is here, and fetch one thing in
 * full — for the documentation and for the blog. The changelog gets a single
 * tool instead, because a release is already small: listing them and fetching
 * one would be two calls to read what fits in the first.
 *
 * The indexes are generated at build time by scripts/build-blog-data.js and
 * bundled with the function — reading the Markdown from disk at request time
 * would not work, because the source tree is not deployed alongside the
 * function.
 *
 * Stateless on purpose: there is no session to keep, every call is a read,
 * and a stateless transport survives being run on whichever instance the
 * platform happens to pick.
 */

const require = createRequire(import.meta.url);
const blogData = require("./blog-data.json");
const docsData = require("./docs-data.json");
const changelogData = require("./changelog-data.json");

const SITE = "https://u4a.ai";
const NAME = "u4a";
const VERSION = "1.0.0";

function createServer() {
  const server = new McpServer({ name: NAME, version: VERSION });

  server.tool(
    "listDocs",
    "List every documentation page on u4a.ai in reading order, with its " +
      "section, group, description and headings. Call this first to find a " +
      "slug for getDoc.",
    {},
    async () => ({
      content: [
        {
          type: "text",
          text: JSON.stringify(
            docsData.map((doc) => ({
              title: doc.title,
              section: doc.section,
              group: doc.group,
              description: doc.description,
              slug: doc.slug,
              url: `${SITE}${doc.url}`,
              markdown: `${SITE}${doc.markdown}`,
              headings: doc.headings,
            })),
            null,
            2
          ),
        },
      ],
    })
  );

  server.tool(
    "getDoc",
    "Get the full Markdown of one documentation page by slug. Use listDocs " +
      "first to find available slugs.",
    {
      slug: z
        .string()
        .describe(
          "The page slug, e.g. 'overview/four-beats' or 'reference/wire-contract'"
        ),
    },
    async ({ slug }) => {
      const wanted = slug.replace(/^\/?docs\//, "").replace(/\/$/, "");
      const doc = docsData.find((d) => d.slug === wanted);

      if (!doc) {
        return {
          content: [
            {
              type: "text",
              text:
                `No documentation page with slug "${slug}". Available: ` +
                docsData.map((d) => d.slug).join(", "),
            },
          ],
          isError: true,
        };
      }

      const header = [
        `# ${doc.title}`,
        "",
        `**Section:** ${doc.section} — ${doc.group}`,
        `**URL:** ${SITE}${doc.url}`,
        "",
        doc.description ? `> ${doc.description}` : "",
        "",
        "---",
        "",
      ].join("\n");

      return { content: [{ type: "text", text: header + doc.body }] };
    }
  );

  server.tool(
    "listChangelog",
    "List releases of the UMA for Agents reference architecture, newest " +
      "first, with the date, version and the changes in each. Optionally " +
      "filter to releases whose text mentions a term, or take the most " +
      "recent few.",
    {
      contains: z
        .string()
        .optional()
        .describe("Only releases whose changes mention this text."),
      limit: z
        .number()
        .int()
        .positive()
        .optional()
        .describe("Return at most this many, newest first."),
    },
    async ({ contains, limit }) => {
      const needle = (contains || "").toLowerCase();
      const hits = changelogData
        .filter((r) => !needle || r.body.toLowerCase().includes(needle))
        .slice(0, limit || 25)
        .map((r) => ({
          date: r.date,
          version: r.version,
          changes: r.changes,
          url: `${SITE}${r.url}`,
          markdown: `${SITE}/changelog.md`,
        }));
      return {
        content: [{ type: "text", text: JSON.stringify(hits, null, 2) }],
      };
    }
  );

  server.tool(
    "listBlogs",
    "List every post on u4a.ai with its title, date, author, category, " +
      "description, tags and URL. Call this first to find a slug for getBlog.",
    {},
    async () => ({
      content: [
        {
          type: "text",
          text: JSON.stringify(
            blogData.map((post) => ({
              title: post.title,
              date: post.date,
              author: post.author,
              category: post.category,
              description: post.description,
              slug: post.slug,
              url: `${SITE}${post.url}`,
              markdown: `${SITE}${post.markdown}`,
              tags: post.tags,
              featuredpost: post.featuredpost,
            })),
            null,
            2
          ),
        },
      ],
    })
  );

  server.tool(
    "getBlog",
    "Get the full Markdown of one post by slug. Use listBlogs first to find " +
      "available slugs.",
    {
      slug: z
        .string()
        .describe(
          "The post slug, e.g. '2026-08-12-deploying-u4a-at-scale'"
        ),
    },
    async ({ slug }) => {
      const post = blogData.find((p) => p.slug === slug);

      if (!post) {
        return {
          content: [
            {
              type: "text",
              text:
                `No post with slug "${slug}". Available: ` +
                blogData.map((p) => p.slug).join(", "),
            },
          ],
          isError: true,
        };
      }

      const header = [
        `# ${post.title}`,
        "",
        `**Author:** ${post.author}`,
        `**Date:** ${post.date}`,
        `**Category:** ${post.category}`,
        `**Tags:** ${(post.tags || []).join(", ")}`,
        `**URL:** ${SITE}${post.url}`,
        "",
        `> ${post.description}`,
        "",
        "---",
        "",
      ].join("\n");

      return { content: [{ type: "text", text: header + post.body }] };
    }
  );

  return server;
}

export default async (req) => {
  // A plain GET is someone checking the endpoint is real, not a protocol
  // call — answer with what this is rather than a transport error.
  if (req.method === "GET") {
    return new Response(
      JSON.stringify({
        name: NAME,
        version: VERSION,
        description:
          "MCP server for u4a.ai. Tools: listDocs, getDoc, listChangelog, " +
          "listBlogs, getBlog. " +
          "Every page is also plain Markdown — /docs/<section>/<page>.md and " +
          "/blog/<slug>.md",
        tools: ["listDocs", "getDoc", "listChangelog", "listBlogs", "getBlog"],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  }

  if (req.method === "DELETE") return new Response(null, { status: 405 });

  try {
    const server = createServer();
    const transport = new WebStandardStreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
    });
    await server.connect(transport);
    return await transport.handleRequest(req);
  } catch (error) {
    console.error("MCP error:", error);
    return new Response(
      JSON.stringify({
        jsonrpc: "2.0",
        error: { code: -32603, message: "Internal server error" },
        id: null,
      }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
};

export const config = { path: "/mcp" };

import React from "react";
import { graphql } from "gatsby";
import Layout from "../components/Layout";
import SEO from "../components/SEO";
import { HTMLContentWithCodeCopy } from "../components/Content";
import TableOfContents from "../components/TableOfContents";
import PageActions from "../components/PageActions";

/**
 * The changelog.
 *
 * Two columns and nothing else: the dates down the side, the entries in the
 * middle. Deliberately not the docs template — a doc is a subject you read
 * through, and this is a list you scan for the day something changed, so the
 * section sidebar and the next/previous footer would both be answering a
 * question nobody has here.
 *
 * The contents are built from the headings the page actually rendered, which
 * is why the article comes first in the markup and the grid puts the list
 * back on the left.
 */
const Changelog = ({ data }) => {
  const page = data.markdownRemark;
  const { title, description } = page.frontmatter;
  const markdownPath = `${page.fields.slug.replace(/\/$/, "")}.md`;

  return (
    <Layout>
      {/* `docPage` marks this as reference material rather than a dated
          post — TechArticle, not BlogPosting. The changelog is one page that
          keeps changing, which is exactly what that type is for. */}
      <SEO
        title={title}
        description={description}
        pathname={page.fields.slug}
        docPage
        breadcrumb={{ section: "Changelog" }}
      />
      <section className="changelog-hero">
        <div className="changelog-hero__inner">
          <h1>{title}</h1>
          <p>{description}</p>
          <PageActions markdownPath={markdownPath} />
        </div>
      </section>

      <div className="changelog-area">
        <div className="changelog-wrapper">
          <div className="changelog-body">
            <HTMLContentWithCodeCopy content={page.html} />
          </div>
          <aside className="changelog-toc">
            {/* The component defaults to the blog's container; this page
                is not that, and a default that silently finds nothing
                renders an empty aside rather than an error. */}
            <TableOfContents containerSelector=".changelog-body" />
          </aside>
        </div>
      </div>
    </Layout>
  );
};

export default Changelog;

export const pageQuery = graphql`
  query ChangelogByID($id: String!) {
    markdownRemark(id: { eq: $id }) {
      id
      html
      fields {
        slug
      }
      frontmatter {
        title
        description
      }
    }
  }
`;

import * as React from "react";
import PropTypes from "prop-types";
import slugify from "../utils/slugify";

export const HTMLContent = ({ content, className }) => (
  <div className={className} dangerouslySetInnerHTML={{ __html: content }} />
);

const COPY_ICON_SVG = `<svg class="blog-code-copy-svg" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v1"/></svg>`;

const COPIED_ICON_SVG = `<svg class="blog-code-copy-svg" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>`;

function attachCodeCopyButtons(container) {
  if (typeof document === "undefined" || !container) return;
  const pres = container.querySelectorAll("pre");
  pres.forEach((pre) => {
    if (pre.querySelector(".blog-code-copy")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "blog-code-copy";
    btn.setAttribute("aria-label", "Copy code to clipboard");
    btn.innerHTML = COPY_ICON_SVG;
    btn.addEventListener("click", () => {
      const code = pre.querySelector("code");
      const text = code ? code.innerText : pre.innerText;
      void navigator.clipboard.writeText(text).then(() => {
        btn.innerHTML = COPIED_ICON_SVG;
        btn.setAttribute("aria-label", "Copied to clipboard");
        window.setTimeout(() => {
          btn.innerHTML = COPY_ICON_SVG;
          btn.setAttribute("aria-label", "Copy code to clipboard");
        }, 2000);
      });
    });
    pre.appendChild(btn);
  });
}

/**
 * Give every h2/h3 an id, in the HTML string, before React renders it.
 *
 * `TableOfContents` used to set these on the live nodes instead. That works
 * exactly once: the first anchor click changes the route hash, React
 * re-renders, `dangerouslySetInnerHTML` replaces the markup, and every id it
 * had written is gone — so the contents list keeps pointing at anchors that
 * no longer exist and nothing moves. Reported on the changelog, latent on
 * every doc and post for the same reason.
 *
 * Ids that are part of the rendered markup survive re-renders, and they are
 * also in the HTML a crawler or a reader-mode sees. The slug rule is shared
 * with the contents list so the two cannot disagree.
 */
function withHeadingIds(html) {
  if (!html) return html;
  const seen = new Map();
  return html.replace(/<(h[23])([^>]*)>([\s\S]*?)<\/\1>/g, (m, tag, attrs, inner) => {
    if (/\sid=/.test(attrs)) return m;
    const base = slugify(inner.replace(/<[^>]+>/g, "")) || "section";
    const n = seen.get(base) || 0;
    seen.set(base, n + 1);
    return `<${tag}${attrs} id="${n ? `${base}-${n}` : base}">${inner}</${tag}>`;
  });
}

/** Same as HTMLContent plus a prod-style Copy control on fenced code blocks. */
export const HTMLContentWithCodeCopy = ({ content, className }) => {
  const ref = React.useRef(null);
  React.useLayoutEffect(() => {
    attachCodeCopyButtons(ref.current);
  }, [content]);
  return (
    <div
      ref={ref}
      className={className}
      dangerouslySetInnerHTML={{ __html: withHeadingIds(content) }}
    />
  );
};

HTMLContentWithCodeCopy.propTypes = {
  content: PropTypes.string,
  className: PropTypes.string,
};

const Content = ({ content, className }) => (
  <div className={className}>{content}</div>
);

Content.propTypes = {
  content: PropTypes.node,
  className: PropTypes.string,
};

HTMLContent.propTypes = Content.propTypes;

export default Content;

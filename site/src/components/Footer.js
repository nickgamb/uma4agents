import React from "react";
import { Link } from "gatsby";
import {
  repo,
  codespace,
  people,
  workGroup,
  footerBlurb,
  tagline,
} from "../data/site";
import { GitHubIcon, LinkedInIcon } from "./Icons";

const Footer = () => (
  <footer className="site-footer">
    <div className="container">
      <div className="site-footer__top">
        <div className="site-footer__about">
          <div className="site-footer__mark">U4A</div>
          <p className="site-footer__blurb">{footerBlurb}</p>

          <a
            className="site-footer__repo"
            href={repo}
            target="_blank"
            rel="noopener noreferrer"
          >
            <GitHubIcon className="icon-gh" />
            <span>github.com/nickgamb/uma4agents</span>
          </a>

          {/* The nav's call to action is a menu, so its contents exist only
              once JavaScript runs. This is the plain, always-rendered path to
              the same place — for a crawler, and for anyone without it. */}
          <a
            className="site-footer__repo"
            href={codespace}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span aria-hidden="true">▶</span>
            <span>Run the Kubernetes lab in Codespaces</span>
          </a>

          <p className="site-footer__label">The people behind it</p>
          <div className="site-footer__people">
            {people.map((p) => (
              <div className="site-footer__person" key={p.name}>
                <a
                  href={p.linkedin}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${p.name} on LinkedIn`}
                >
                  <LinkedInIcon className="icon-li" />
                  <span>{p.name}</span>
                </a>
                {p.org && (
                  <a
                    className="site-footer__org"
                    href={p.org.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {/* Their own mark rather than a generic glyph, and a
                        plain <img> rather than an inline component: these
                        are two other companies' brands, so they are assets
                        we serve, not shapes we redraw. */}
                    <img
                      className="icon-org"
                      src={p.org.icon}
                      alt=""
                      width="16"
                      height="16"
                      loading="lazy"
                    />
                    <span>{p.org.name}</span>
                  </a>
                )}
              </div>
            ))}
          </div>

          <p className="site-footer__label">Where the standard is made</p>
          <div className="site-footer__people">
            <a href={workGroup.url} target="_blank" rel="noopener noreferrer">
              <img
                className="icon-org"
                src={workGroup.icon}
                alt=""
                width="16"
                height="16"
                loading="lazy"
              />
              <span>{workGroup.name}</span>
            </a>
            <a href={workGroup.join} target="_blank" rel="noopener noreferrer">
              <span>Join the work group, free &rarr;</span>
            </a>
          </div>
        </div>

        {/* The code you can scan from a slide. */}
        <div className="site-footer__qr">
          <a href={repo} aria-label="QR code to the repository">
            <img
              src="/qr.svg"
              alt="QR code linking to the UMA for Agents repository"
              width="118"
              height="118"
            />
          </a>
          <p>Scan for the lab</p>
        </div>
      </div>

      <div className="site-footer__bottom">
        <span>&copy; {new Date().getFullYear()} UMA for Agents</span>
        <span className="site-footer__tagline">{tagline}</span>
        <Link className="link-arrow" to="/contact/">
          Get in touch &rarr;
        </Link>
      </div>
    </div>
  </footer>
);

export default Footer;

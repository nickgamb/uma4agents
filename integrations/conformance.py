"""Is this endpoint actually U4A-ready?

Run it against a resource you have put an enforcement point in front of. It
asserts the obligations from *outside*, in the order an agent meets them, and
it is deliberately unkind: a suite that only proves the allows would pass
against an endpoint with no enforcement at all.

    python3 conformance.py https://billing-mcp.example.com

Optionally, to check the last and most-often-missed obligation — that the
resource cannot be reached around the enforcement point:

    python3 conformance.py https://billing-mcp.example.com \\
        --upstream http://n8n.internal:5678/mcp/abc123

Needs only httpx. Nothing else, and no credentials: everything here is what an
agent that has never been introduced can see.
"""

from __future__ import annotations

import json
import sys
from urllib.parse import urljoin, urlparse

import httpx

PASS, FAIL, WARN = [], [], []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"\n       {detail}" if detail and not ok else ""))
    return ok


def warn(name: str, detail: str = "") -> None:
    WARN.append(name)
    print(f"  warn {name}" + (f"\n       {detail}" if detail else ""))


def rpc(client: httpx.Client, url: str, method: str, params: dict,
        headers: dict | None = None):
    return client.post(url, json={"jsonrpc": "2.0", "id": 1,
                                  "method": method, "params": params},
                       headers={"content-type": "application/json",
                                "mcp-protocol-version": "2025-06-18",
                                **(headers or {})})


def mcp_call(client: httpx.Client, url: str, tool: str,
             headers: dict | None = None):
    """A tools/call an agent with no grant would make."""
    return rpc(client, url, "tools/call", {"name": tool, "arguments": {}},
               headers)


def fetch_prm(client: httpx.Client, base: str) -> tuple[dict, str]:
    """The resource's own metadata document, and where it was found.

    Tried at the two well-known locations before any call is made, because it
    is also where the tool surface is published — and reading it first is what
    an agent does. `tools/list` is not a substitute: it is usually protected
    itself, so it answers with a challenge rather than a list.
    """
    for path in (f"/.well-known/oauth-protected-resource{urlparse(base).path}",
                 "/.well-known/oauth-protected-resource"):
        url = f"{urlparse(base).scheme}://{urlparse(base).netloc}{path}"
        try:
            r = client.get(url)
            if r.status_code == 200 and isinstance(r.json(), dict):
                return r.json(), url
        except Exception:                                       # noqa: BLE001
            continue
    return {}, ""


def tool_from(doc: dict) -> str | None:
    """A tool this endpoint says it exposes.

    Probing an invented name is not the same test. A correct enforcement point
    refuses a tool it has never heard of *without* a challenge — there is no
    resource to negotiate for — so an invented name measures the wrong thing
    and reports a healthy endpoint as broken.
    """
    for surface in doc.get("tool_surfaces") or []:
        if isinstance(surface, dict) and surface.get("tool"):
            return surface["tool"]
    return None


def main(base: str, upstream: str | None) -> int:
    base = base.rstrip("/")
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:

        print("\n== 1 · An unauthorized call is challenged ==")
        doc, doc_url = fetch_prm(client, base)
        tool = tool_from(doc)
        if tool:
            print(f"  ---- probing {tool!r}, which its own document publishes")
        else:
            tool = "any_tool"
            warn("the endpoint publishes no tool surface, so this probes a "
                 "placeholder name",
                 "an enforcement point is right to refuse an unknown tool "
                 "without a challenge, so what follows may report a healthy "
                 "endpoint as broken.")
        try:
            r = mcp_call(client, base, tool)
        except httpx.RequestError as exc:
            print(f"  FAIL could not reach {base}: {exc}")
            return 1

        challenged = check("it answers 401 rather than serving the call",
                           r.status_code == 401,
                           f"got {r.status_code}. A 200 here means the endpoint "
                           f"is unprotected; a 403 means it refused without "
                           f"telling the agent how to proceed.")
        www = r.headers.get("www-authenticate", "")
        check("the challenge is a UMA challenge", "UMA" in www,
              f"WWW-Authenticate was {www!r}")
        check("it names an authorization server", "as_uri=" in www,
              "without as_uri an agent has nowhere to negotiate")
        check("it carries a ticket", "ticket=" in www,
              "without a ticket the agent cannot start the grant")
        has_prm = check("it points at its metadata document",
                        "resource_metadata=" in www,
                        "an agent should be able to corroborate as_uri against "
                        "the resource's own document rather than trust this header")

        print("\n== 2 · The metadata document holds up ==")
        # Prefer the document the challenge itself pointed at: that is the one
        # an agent would read, and if it differs from the well-known location
        # this is where that shows up.
        if has_prm:
            named = www.split("resource_metadata=")[1].split(",")[0].strip('" ')
            try:
                r_doc = client.get(named)
                if r_doc.status_code == 200:
                    doc, doc_url = r_doc.json(), named
            except Exception:                                   # noqa: BLE001
                pass
        check("a metadata document is published and fetchable", bool(doc),
              "tried the challenge's resource_metadata and both well-known "
              "locations")

        resource = doc.get("resource", "")
        check("it declares the resource it is for", bool(resource))
        # RFC 9728 3.3: a client must refuse a document that names a resource
        # other than the one it is accessing. This is the single most common
        # way one of these deployments is subtly broken.
        check("and that matches the URL agents actually use",
              bool(resource) and urlparse(resource).netloc == urlparse(base).netloc,
              f"the document claims {resource!r}, which an agent reaching "
              f"{base} is required by RFC 9728 to reject. Set the sidecar's "
              f"public base to the URL agents type.")
        servers = doc.get("authorization_servers") or []
        check("it names an authorization server", bool(servers))
        if servers and "as_uri=" in www:
            named = www.split("as_uri=")[1].split(",")[0].strip('" ')
            check("and it is the same one the challenge named",
                  any(named.rstrip("/") == s.rstrip("/") for s in servers),
                  f"challenge said {named}, document says {servers}")
        # The authority the resource names says what it speaks. UMA 2.0 Grant
        # section 4 has a server that supports a profile advertise its URI;
        # an agent reading this before it has sent anything learns that the
        # party behind the challenge negotiates the way this profile says.
        for as_uri in servers[:1]:
            meta = {}
            for path in ("/.well-known/uma2-configuration",
                         "/.well-known/uma4agents-configuration"):
                try:
                    r = client.get(as_uri.rstrip("/") + path, timeout=10.0)
                    if r.status_code == 200:
                        meta = r.json()
                        break
                except (httpx.HTTPError, ValueError):
                    continue
            profiles = meta.get("uma_profiles_supported") or []
            check("and that authorization server says it implements this profile",
                  "https://u4a.ai/spec/core/1.0" in profiles,
                  f"uma_profiles_supported: {profiles or 'absent'}")

        print("\n== 3 · A grant is not taken on faith ==")
        bad = mcp_call(client, base, tool,
                       {"Authorization": "Bearer not-a-real-grant"})
        check("a made-up bearer token does not get through",
              bad.status_code in (401, 403),
              f"got {bad.status_code}, which means the token was not checked")

        # A structurally valid but unsigned request. The grant is bound to a
        # key; without a signature over the request there is nothing tying the
        # call to the holder of that key.
        check("and neither does one without a proof-of-possession signature",
              bad.status_code in (401, 403) and "signature" not in bad.request.headers)

        print("\n== 4 · The enforcement point cannot be walked around ==")
        if not upstream:
            warn("upstream reachability not checked",
                 "pass --upstream <internal MCP url> to assert it. This is the "
                 "obligation most often missed: everything above can pass "
                 "while the resource is still reachable directly.")
        else:
            try:
                direct = mcp_call(client, upstream.rstrip("/"), tool)
                reachable = direct.status_code < 500
            except httpx.RequestError:
                reachable = False
            check("the resource itself refuses a call that did not come "
                  "through the enforcement point", not reachable,
                  f"{upstream} answered directly. Everything above is advisory "
                  f"until this is closed — put the upstream in a network only "
                  f"the enforcement point can reach.")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f", {len(WARN)} not checked" if WARN else ""))
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("\nThis endpoint answers the protocol, publishes a document that")
    print("corroborates it, and refuses what it has no reason to allow.")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    up = None
    if "--upstream" in sys.argv:
        i = sys.argv.index("--upstream")
        up = sys.argv[i + 1] if len(sys.argv) > i + 1 else None
    raise SystemExit(main(args[0], up))

# The specification set

Nine Internet-Drafts profiling and extending UMA 2.0 for autonomous agents,
written from this lab. Source is `src/*.md` in kramdown-rfc Markdown; rendered
`.txt`, `.html` and `.xml` are in `../site/static/spec/` and published at
https://u4a.ai/spec/.

| Draft | Title | In the set |
|---|---|---|
| `draft-gamb-uma4agents-core-00` | User-Managed Access (UMA) 2.0 Profile for Autonomous Agents | Required |
| `draft-gamb-uma4agents-terms-00` | Owner-Proffered Terms for UMA 2.0 | Required |
| `draft-gamb-uma4agents-fedauthz-00` | Federated Authorization for Autonomous Agents | Required |
| `draft-gamb-uma4agents-policy-00` | Owner Policy, Assurance and Attention | Optional |
| `draft-gamb-uma4agents-lineage-00` | Agent Lineage | Optional |
| `draft-gamb-uma4agents-multiparty-00` | Multi-Party Authorization | Optional |
| `draft-gamb-uma4agents-owner-00` | The Resource Owner's API | Optional |
| `draft-gamb-uma4agents-mcp-00` | Model Context Protocol Binding | Binding |
| `draft-gamb-uma4agents-aauth-00` | AAuth Binding | Binding |

Each has an identifying URI (`https://u4a.ai/spec/<part>/1.0`, listed in
`lib/uma4a_profiles.py`), and the authorization server advertises the ones it
implements in `uma_profiles_supported`.

## Rendering

```
make spec         # kramdown-rfc → xml2rfc, in a container, into site/static/spec
make spec-check   # every normative statement mapped to the check that proves it
```

`.refcache/` holds the bibliographic XML for every reference and is committed,
so a render reaches no network. A new reference is fetched once, on the first
render that cites it, and the fetched file is committed with the change.

## The requirements register

`conformance.yaml` maps every MUST, MUST NOT, SHALL and SHALL NOT in the
rendered drafts to what verifies it: a make target and the assertion it
prints, or the statement that the requirement is on a deployment or a binding
rather than on this implementation. `check_conformance.py` fails the build if
a normative statement has no row, a row names a check that does not exist, or
a row's quoted text is no longer in the draft.

The drafts are grounded in `docs/`, `FINDINGS.md` and the code, in that
direction: where a draft and the repo disagreed while writing, the repo was
corrected in the same change.

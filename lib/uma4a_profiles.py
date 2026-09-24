"""The identifying URIs of the specification set this implementation follows.

UMA 2.0 Grant section 4 asks that a profile or extension be given a uniquely
identifying URI, and that an authorization server supporting one advertise it
in its `uma_profiles_supported` metadata. These are those URIs, one per
document in the set, dereferenceable to the document an implementer needs.

Kept in `lib/` because more than one party advertises them: the authorization
server speaks the whole set, and the tally speaks the parts a counting party
needs.
"""

CORE = "https://u4a.ai/spec/core/1.0"
TERMS = "https://u4a.ai/spec/terms/1.0"
FEDAUTHZ = "https://u4a.ai/spec/fedauthz/1.0"
POLICY = "https://u4a.ai/spec/policy/1.0"
LINEAGE = "https://u4a.ai/spec/lineage/1.0"
MULTIPARTY = "https://u4a.ai/spec/multiparty/1.0"
OWNER = "https://u4a.ai/spec/owner/1.0"
MCP = "https://u4a.ai/spec/mcp/1.0"
AAUTH = "https://u4a.ai/spec/aauth/1.0"

# What the reference authorization server implements: the three required
# documents, every optional extension, and the one binding that places
# obligations on an authorization server. The AAuth binding does; the MCP
# binding governs how a challenge travels between agent and resource, and asks
# nothing of the authority, so an authority does not list it.
AUTHORIZATION_SERVER = [CORE, TERMS, FEDAUTHZ, POLICY, LINEAGE, MULTIPARTY, OWNER,
                        AAUTH]

# What a tally implements. It speaks the core surface to a requesting agent,
# proffers folded terms, and is the counting party of the multi-party
# extension; it evaluates no owner policy and admits no lineage.
TALLY = [CORE, TERMS, MULTIPARTY]

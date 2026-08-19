// The words every animated figure says, as data.
//
// These captions are the figure's actual explanation — the motion illustrates
// them — so they cannot live only inside a React component. Three other things
// need to read them: the Markdown twin published beside each page, the search
// index, and the MCP payload an agent fetches. A site whose whole argument is
// that agents should be able to read it cannot keep a layer of its content in
// JSX that only a browser can run.
//
// CommonJS for the same reason as src/data/docs-nav.js and src/style/theme.js:
// webpack bundles it for the app, and plain Node requires it from
// scripts/build-blog-data.js and gatsby-node.js, under a pinned Node 20 that
// cannot require an ES module.
//
// src/components/DocDiagram.js zips these into its scenes by index and throws
// if the counts disagree, so a scene added without a caption fails the build
// rather than rendering an empty one.

const figureScripts = {
  "four-beats": {
    title: "The four beats",
    steps: [
      "Bob's agent calls a protected tool. It holds no grant, so nothing about the call is allowed yet.",
      "The enforcement point registers the attempt with Alice's authority, then refuses — handing back a ticket and the address of the authority that could grant it.",
      "The agent presents the ticket. Instead of a grant it gets Alice's terms, and a fresh ticket — every presentation rotates it.",
      "It signs the terms and presents again. Alice is asleep, so the negotiation waits on her — the agent holds a ticket rather than a call.",
      "She approves. The grant is bound to that one order, and the agent retries the original call with its signature over it.",
    ],
  },
  "who-answers": {
    title: "Who has standing to answer",
    steps: [
      "Bob's advisor sends an agent to Alice's holdings. The agent is not a villain — it is simply not Alice, and that is enough to need a negotiation.",
      "Bob can answer for Bob. He has no standing to answer for Alice — he is her advisor, not her.",
      "Meridian holds the assets and can refuse the call. It cannot decide, because the policy is not its to read — and it answers to a thousand other owners too.",
      "Only the authority on Alice's side can answer, and it can answer at three in the morning, because what it holds is her policy rather than her attention.",
    ],
  },
  "terms-exchange": {
    title: "The terms exchange",
    steps: [
      "Alice's authority does not ask what the agent will accept. It proffers her terms: the purpose, the scope, how long, and what is forbidden — as a document at a URL that keeps working.",
      "The agent echoes the template back, signed with the key it will later use to prove possession of the grant. One key, two jobs — so the party that committed is the party that calls.",
      "The echo is checked field by field. A valid signature over weaker terms is exactly what an adversarial agent would send, so a dropped prohibition or a stretched expiry ends the negotiation.",
      "On grant, her authority returns a receipt that embeds the agent's signed agreement and counter-signs it. Both sides now hold the same dually-signed record, and neither can produce a version the other cannot check.",
    ],
  },
  "two-intents": {
    title: "One agent, as it appears in the owner's own record",
    steps: [
      "Alice writes her terms before any agent exists. They name what the access is for, what she will not have done with it, how far it reaches and for how long — and they name no agent, so they hold for whoever turns up.",
      "An agent turns up, signs those terms, says why it is asking, and reads what it asked for. Two rows: what it promised, and what it then did. Both are hers, on her side, whether or not anyone reports anything to her.",
      "It keeps going. Every row is at the same tier, which is the boring case and the one that should stay boring — what it did and what it said it wanted are the same shape.",
      "Then a row at a tier it has never reached. Nobody had to tell her: the widening is a fact about her own register, and a rule she wrote — ask me the first time an agent reaches somewhere new — reads exactly that.",
    ],
  },

  "identity-vs-authz": {
    title: "Identity is not authorization",
    steps: [
      "A verified agent identity is worth having. It tells you which agent this is across sessions, who operates it, and that it holds the key it claims.",
      "None of that says whether the owner agreed, on what terms, or how she withdraws it. A perfectly identified agent is still an agent standing at a door that has not been opened.",
      "That is the division of labour: identity work answers who is asking, and the grant answers whether they may. This profile consumes the first rather than competing with it.",
    ],
  },
  "discovery-layers": {
    title: "Public and protected discovery",
    steps: [
      "The public document is structural: what tools exist, what scopes they need, which authorization servers speak for this resource, and the keys its metadata is signed under. Anyone may fetch it.",
      "Whose instances sit behind the resource is a different kind of fact, and it is served only to a caller that proves possession of the owner's authorization server key.",
      "Publishing that lower band openly would tell anyone who asks which resources Alice owns — a leak the older push-registration model never had.",
    ],
  },
  "proof-of-possession": {
    title: "Proof-of-possession",
    steps: [
      "The grant names the agent's public key. Every call carries a signature over the method, the authority, the path, the authorization header and a digest of the body.",
      "Copy the token and you have a string. Without the private key there is no signature that verifies against the key the grant names, so the call is refused before it reaches the resource.",
      "Nor can the holder change the call after signing it. The body is covered by a digest inside the signature base, so an edited request fails verification rather than passing with new arguments.",
    ],
  },
  "single-use-race": {
    title: "Two replicas, one grant",
    steps: [
      "Alice approved one trade. Under load, two copies of the same call reach two replicas of the authorization server.",
      "Read, then decide, then write. Both replicas read the flag, and both of them read false.",
      "Both write true. Both are told yes. From each replica's point of view nothing went wrong, so nothing is logged.",
      "One statement instead: update the row only if it is still unspent, and return what changed.",
      "One caller gets a row back and proceeds. The other gets nothing, and a caller that gets nothing denies.",
    ],
  },
  "revoke-cascade": {
    title: "Revocation",
    steps: [
      "A standing connection, and the live grants issued under it. This is what Alice sees: a relationship with one agent, not a list of tokens.",
      "She revokes it. Ending the relationship and burning every grant behind it happen in one operation — as two steps the second can fail on its own, leaving the agent holding exactly the authority she just withdrew.",
      "An agent presenting one of them is told so explicitly, and the answer is terminal. Re-negotiating cannot change an outcome she has already settled, and a bare inactive would send it round the loop again.",
    ],
  },
  "trust-boundary": {
    title: "The trust boundary",
    steps: [
      "Two parties, and a line between them. Alice's side holds the policy, the terms and the record; Meridian's side holds the assets and the component that refuses.",
      "Meridian's enforcement point is allowed across the line for exactly three things: take a ticket, ask whether a grant is live, and spend it.",
      "Reading her policy is refused — on the same port, from the same workload, as the call that was just permitted. That pair is the whole cross-principal argument, and it is something CI can fail on.",
    ],
  },
  "roles-map": {
    title: "The six roles",
    steps: [
      "1. An authority on her side — Holds her policy, dictates terms, mints grants, and answers while she is offline. Judge it by who can change the rules, not by where it runs.",
      "2. An enforcement point — Refuses before forwarding, returns a ticket, verifies a signature, and spends a single-use grant. Judge it by whether its callout can control the response body, not just the verdict.",
      "3. A resource that says what it is — Publishes its tool surfaces, its scopes, and which authorization servers speak for it. Usually the cheapest role to fill: the resource itself does not have to change.",
      "4. Somewhere to store single-use state — Decides and records in one indivisible operation, and reports who won. If you would write this as read-then-write, it is the wrong store.",
      "5. A way to reach her — Notifies her, shows what is asked and on what terms, takes a decision, releases the hold. Judge it by latency tolerance — she may be asleep for hours.",
      "6. An identity for the agent — Gives the agent a stable name her authority recognises across sessions. Judge it by whether the name survives key rotation.",
    ],
  },
  "enforcement-order": {
    title: "The enforcement order",
    steps: [
      "Introspect, without consuming. Is the token live, and does the connection behind it still stand?",
      "Scope. Does the tool being called map to a permission this grant actually carries?",
      "Signature. Does the request verify against the key named in the grant? This is the step that makes it proof-of-possession rather than bearer.",
      "Operation. For a single-use grant, do the parameters hash to exactly what Alice approved?",
      "Consume. Only now is the grant spent — atomically, and a caller that loses the race denies.",
      "Move the burn to the top and it runs before any check does. Anyone who observes the token can replay it unsigned and destroy an approval Alice personally gave.",
    ],
  },
  "two-hosts": {
    title: "One core, two hosts",
    steps: [
      "A gateway in front of the resource asks an external authorization service for a verdict before it forwards anything. Most meshes and API gateways have a mechanism for exactly this.",
      "Or the same logic runs inside the resource itself, as middleware, with no gateway in the authorization path at all. Both are conformant, and your stack usually decides which.",
      "What must not happen is two implementations. Express the decision against plain facts — method, authority, path, digest, token, tool and arguments — and each host only converts its own request in and its own response out.",
    ],
  },
  "rogue-challenge": {
    title: "A challenge you must not trust",
    steps: [
      "A refusal arrives naming the authorization server to negotiate with. Anything able to return a 401 can name one, including something that is not the resource at all.",
      "So the agent fetches the resource's published metadata, which lists the authorization servers the resource actually claims. That document is signed and served over TLS by the resource itself.",
      "If the challenge names an authority the resource never published, refuse it. Without this check an attacker sends the agent off to sign terms and present credentials to a server of their choosing — and the check is two lines.",
    ],
  },
  "standards-map": {
    title: "Which specification supplies which piece",
    steps: [
      "The base is UMA 2.0 and FedAuthz over OAuth 2.0, with OpenID Connect for how the owner authenticates to her own authority. The grant type, the ticket and the party split all come from here.",
      "Four RFCs make the grant hold: 9728 publishes what the resource is, 9421 proves possession on every request, 7638 gives a pseudonymous agent a stable name, and 9396 gives the challenge a structure.",
      "IEEE 7012 is the one that changes the character of the thing. Without it this is a well-bound token; with it, the owner is stating requirements rather than a service offering conditions.",
      "Agent identity work — AAuth, Web Bot Auth, CIMD — is consumed rather than competed with. All of it answers who is asking, and none of it ever becomes an authorization input.",
    ],
  },
  "compare-uma": {
    title: "Keep, change, add",
    steps: [
      "Most of UMA 2.0 carries unchanged. The cross-principal topology is the idea the rest hangs off and nothing else on the table has it; the permission ticket and the pending state come through clean.",
      "Three things change shape. Claims-gathering becomes the owner proffering terms rather than naming formats, the RPT keeps its semantics but drops bearer for proof-of-possession, and registration becomes something the authority pulls.",
      "Two things are genuinely new, and both come from the agent era rather than from the specification: grants bound to one operation and spent once, and the owner's own app as the surface where she is asked.",
    ],
  },
};

/** The steps for one figure, or an empty list if it has none. */
const scriptFor = (name) => (figureScripts[name] || {}).steps || [];

/** The figure's own title, for the Markdown twin's heading. */
const titleFor = (name) => (figureScripts[name] || {}).title || null;

module.exports = { figureScripts, scriptFor, titleFor };

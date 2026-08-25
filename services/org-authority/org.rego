# The organization's decision, evaluated by OPA.
#
# This is the layer above the member. Alice's authorization server decides
# what *she* permits; this decides what her employer permits, and a request
# has to survive both. Neither can widen the other — with one stated
# exception, break-glass, which is not decided here at all: it does not
# arrive as an agent's request and never reaches this module.
#
# The asymmetry is structural rather than a convention:
#
#   * this module produces only `refuse` and `ask`. There is no rule shape
#     that can produce a grant, so no charter and no admin's Rego can make a
#     request easier than the member's own policy already makes it;
#   * `data.u4a.custom` is where an admin's own rules land, and it is read
#     for exactly those two sets. A custom module is a sibling package rather
#     than a child of this one so that reading it is not a package depending
#     on itself.
#
# Input is one request, already reduced to facts by the member's authority:
#
#   input.member                 who is being asked about
#   input.charter.conditions     the declarative front end an admin edits in
#                                the console without opening this file
#   input.charter.envelope       the ceiling, for the checks worth making
#                                twice (see always_ask below)
#   input.role                   the group the member is in — its id, its
#                                grants, and what it lets her delegate to an
#                                agent
#   input.request                resource, scopes, expiry, reason, mission,
#                                assurance axes, standing
#
# On why both a charter and an engine:
#
# The charter is the bargain. It is versioned, it is shown to a member in
# full before she joins, and she agrees to it by name — the organization's
# counterpart to the terms she proffers her own agents. What it may say is
# therefore deliberately small, because it is a document people read.
#
# These rules are the organization's operating controls. A member is told
# they exist and is shown the sentence of any rule that stops her; she is not
# shown them line by line, because they are not part of what she agreed to.
# They can only ever refuse or interrupt, so nothing here can change the
# bargain without changing the charter.
#
# The test for which layer a rule belongs in is whether a member would have
# to agree to it again. Widening what a group may reach: charter. A close
# period, market hours, a limit this firm is trying for a quarter: here.
# The two are joined by `input.role` — the charter says what a group is and
# this decides using it, which is a thing neither half can do alone.
package u4a.org

import rego.v1

conditions := object.get(input, ["charter", "conditions"], {})

envelope := object.get(input, ["charter", "envelope"], {})

assurance := object.get(input, ["request", "assurance"], {})

# --- Assurance floors --------------------------------------------------------
#
# Evidence the requesting side supplied may only ever raise a bar, which is
# why every one of these lands in `refuse` and none of them anywhere else.

floors := {
	"binding": {
		"floor": object.get(conditions, "min_binding", 0),
		"level": object.get(assurance, "binding", 0),
		"what": "the request is not bound to a key the authority verified",
	},
	"provenance": {
		"floor": object.get(conditions, "min_provenance", 0),
		"level": object.get(assurance, "provenance", 0),
		"what": "the agent's credential cannot be traced to an issuer",
	},
	"accountability": {
		"floor": object.get(conditions, "min_accountability", 0),
		"level": object.get(assurance, "accountability", 0),
		"what": "nobody the organization can name is standing behind the agent",
	},
}

refuse contains msg if {
	some axis, f in floors
	f.level < f.floor
	msg := sprintf("%s (%s %d, the organization requires %d)", [f.what, axis, f.level, f.floor])
}

# --- What the request has to say for itself ---------------------------------

refuse contains msg if {
	conditions.require_reason
	not stated_reason
	msg := "the agent did not say what it wants the access for, and the organization requires a stated reason"
}

stated_reason if {
	reason := object.get(input, ["request", "reason"], "")
	trim_space(reason) != ""
}

refuse contains msg if {
	conditions.require_mission
	not object.get(input, ["request", "mission"], false)
	msg := "the agent cited no mandate for its errand, and the organization requires one"
}

# --- The ceiling, checked a second time -------------------------------------
#
# `always_ask` and `max_expires_in` are already clamped into the member's own
# terms before an agent ever sees them — that is the envelope's whole job, and
# it is what makes the ceiling visible in the terms document the agent signs.
#
# They are checked again here because the two mechanisms fail in different
# directions. A clamp that did not run leaves a member's terms too generous
# and nothing would notice; this notices. A member's authority that declines
# to clamp at all is the case the enforcement point catches, which is a third
# place and deliberately so.

refuse contains msg if {
	ceiling := envelope.max_expires_in
	requested := object.get(input, ["request", "expires_in"], 0)
	requested > ceiling
	msg := sprintf("the grant would last %ds, past the organization's ceiling of %ds", [requested, ceiling])
}

refuse contains msg if {
	allowed := envelope.allowed_scopes
	some scope in object.get(input, ["request", "scopes"], [])
	not scope in allowed
	msg := sprintf("%s is not a scope the organization allows", [scope])
}

ask contains msg if {
	some pattern in object.get(envelope, "always_ask", [])
	glob.match(pattern, ["/"], object.get(input, ["request", "resource_id"], ""))
	msg := sprintf("the organization requires you to be asked for %s", [pattern])
}

# --- Whose agent is asking ---------------------------------------------------
#
# The rule an organization actually wants and cannot express anywhere else.
#
# Every authorization system can say *what* may be accessed. This says *whose
# agent* may do the accessing on behalf of *which* person — which is a
# distinction about parties, and it only exists because the member's authority
# already knows the difference between an agent she operates and an agent
# somebody else operates, and told us.
#
#   none              she may reach the firm's book herself; no agent may
#   first-party-only  an agent she operates may; somebody else's may not
#   any-agent         any agent may, subject to her terms and this charter
#
# `standing.first_party` is not something the requesting side can assert. It
# holds when the operator the agent names is an origin the member claimed AND
# her authority found this agent's key in that operator's own directory. That
# is her decision plus a check she ran, which is why a rule may rest on it.

delegation := object.get(input, ["role", "delegation"], "none")

refuse contains msg if {
	delegation == "none"
	msg := "this member's role does not let any agent act on the organization's resources — only she can"
}

refuse contains msg if {
	delegation == "first-party-only"
	not object.get(input, ["request", "standing", "first_party"], false)
	msg := "this member's role only lets agents she operates herself act on the organization's resources"
}

# --- The admin's own rules ---------------------------------------------------
#
# Undefined when no custom module is loaded, which is the common case and must
# not be an error: an organization that writes no Rego gets the conditions
# above and nothing else.

custom_deny := d if d := data.u4a.custom.deny

custom_ask := a if a := data.u4a.custom.ask

refuse contains msg if {
	some m in custom_deny
	msg := m
}

ask contains msg if {
	some m in custom_ask
	msg := m
}

# --- The verdict -------------------------------------------------------------
#
# Restrictions beat everything, and there is nothing else — the member's
# authority supplies the permissive half. `because` carries the reasons
# rather than only the outcome, because they end up in the member's ledger
# and in the dialog she is shown, and "your organization said no" without a
# sentence after it is not something a person can act on.

default decision := {"effect": "allow", "because": []}

decision := {"effect": "refuse", "because": sort(refuse)} if count(refuse) > 0

decision := {"effect": "ask", "because": sort(ask)} if {
	count(refuse) == 0
	count(ask) > 0
}

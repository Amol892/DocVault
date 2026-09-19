# 01 — Project Objective

**DocVault** is a multi-tenant document workspace platform for any team or organization. It replaces the ad-hoc pattern of emailing attachments and re-sharing personal-drive folders with three guarantees:

1. **Safe, durable storage** for a user's own documents.
2. **Controlled external sharing** — a single document, via an unguessable, revocable link, to someone outside the organization, without exposing anything else.
3. **Isolated team workspaces** — an organization creates a workspace, invites its own people, organizes documents there, and is guaranteed that no other organization on the platform can see it. A logged-in user sees only the workspaces they created or were explicitly added to — nothing else exists for them.

The product succeeds if a small team can stop passing files around one at a time and instead trust one shared, access-controlled home for their documents — and if that trust holds even as the platform serves many unrelated organizations at once.

**Non-goals for v1** (see [07-functional-requirements.md](./07-functional-requirements.md) for the full scope, and [05-role-model.md](./05-role-model.md) §"why four roles" for the reasoning behind this list):
- Custom/configurable roles or a general permissions matrix beyond the four fixed roles
- SSO (SAML/OIDC) or SCIM provisioning
- Cross-workspace "organization" grouping with shared billing
- Real-time collaborative document editing

Related: [02-tech-stack.md](./02-tech-stack.md) for how it's built, [03-architecture.md](./03-architecture.md) for the system design.

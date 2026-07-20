# VideoBox Hermes Codex OAuth Bootstrap Design

## Goal

Enable a VideoBox-owned Hermes Agent to complete official `openai-codex`
ChatGPT subscription OAuth and select `gpt-5.5`, without copying, mounting,
or reading credentials owned by AK-System, the host Hermes installation, or
any other project.

This design creates an OAuth bootstrap boundary only. It does not authorize a
GPT inference request, project-data transfer, editing mutation, rendering,
export, CapCut access, or an ordinary VideoBox API route.

## Chosen design

Add a distinct `hermes-oauth-bootstrap` Compose profile alongside the existing
`hermes-preauth` profile.

- The existing pre-auth service remains `network_mode: none`, uses only its
  scratch volume, and never runs OAuth.
- The bootstrap service uses the pinned Hermes image and a new VideoBox-only
  named auth-state volume. It never mounts the pre-auth scratch volume, any
  host Hermes directory, VideoBox data, snapshots, PostgreSQL, the workspace
  API, a Docker socket, or a host bridge.
- Bootstrap egress is deny-by-default. The service may reach the official
  Codex OAuth flow only through a separately named egress gateway and
  non-secret destination allowlist. Direct external networks are not attached
  to Hermes.
- The interactive operator runs Hermes' official `openai-codex` OAuth command
  inside the bootstrap container and chooses `gpt-5.5`. Credentials stay in
  the dedicated named volume; they are never printed, exported, copied into
  a repository file, `.env`, database, snapshot, audit record, or memory.
- A later runtime profile may consume this volume only after the gateway,
  per-request project text-only consent, budget, audit, and capability gates
  are separately implemented and approved. Until then, OAuth state cannot
  trigger model calls.

## Rejected designs

1. Bind-mounting the host `~/.hermes` or reusing AK-System credentials would
   merge credential ownership across projects and is forbidden.
2. Changing the existing pre-auth service to allow networking would erase the
   static preflight boundary and is forbidden.
3. Giving Hermes unrestricted internet access would violate the deny-by-default
   egress contract and is forbidden.
4. Implementing an OpenAI OAuth flow in VideoBox is forbidden. Hermes owns the
   official `openai-codex` device-code flow.

## Security and operational rules

- The auth volume is credential state, not VideoBox SSOT and not a backup.
- OAuth create, reuse, expiry, logout, and revoke are exercised only through
  official Hermes CLI behavior. Tests must prove no credential appears in
  logs, inspect output, configuration, or repository artifacts.
- The egress gateway has no access to VideoBox data, and bootstrap requests
  include no project text, media, transcript, caption, or prompt.
- The bootstrap command is interactive and user-operated. A successful login
  records only a redacted outcome and pinned Hermes image/model identifier.
- Any gateway, volume, or credential error fails closed. It cannot fall back to
  host credentials, a generic OpenAI API key, another provider, or an
  unrestricted network.

## Acceptance criteria

1. Compose inspection proves pre-auth and OAuth volumes are different and
   Hermes has no VideoBox/host data mounts.
2. The OAuth profile has no direct external network and uses only the named
   gateway/allowlist path.
3. A bootstrap smoke contract proves the official Hermes command is available,
   but automated tests never complete OAuth or call GPT.
4. Static and runtime checks prove no credentials are present in source,
   `.env`, logs, database, snapshots, or ordinary `/api/*` responses.
5. `logout`, revoke, expiry, and restart leave inference disabled and do not
   alter VideoBox project truth.
6. `gpt-5.5` is the configured bootstrap default only after the operator sees
   it in the account's official Hermes picker; an unavailable model blocks the
   bootstrap rather than silently substituting another model.

## Out of scope

- GPT inference, prompt/project-data transfer, consent UI, budgets, audit
  persistence, capability issuer deployment, gateway API activation, MCP,
  memory, editing mutation, rendering/export, and CapCut/host bridge work.

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
`hermes-preauth` profile. For the local single-user MVP, bootstrap has its own
egress-only Docker network; the separately allowlisted egress gateway remains
the next hardening slice and is not a prerequisite for completing the local
interactive login.

- The existing pre-auth service remains `network_mode: none`, uses only its
  scratch volume, and never runs OAuth.
- The bootstrap service uses the pinned Hermes image and a new VideoBox-only
  named auth-state volume. It never mounts the pre-auth scratch volume, any
  host Hermes directory, VideoBox data, snapshots, PostgreSQL, the workspace
  API, a Docker socket, or a host bridge.
- Bootstrap attaches only to a dedicated egress network. It has no route to
  VideoBox internal services or host mounts. This is deliberately a
  local-MVP speed tradeoff, not an allowlisted production egress guarantee;
  the later egress-gateway slice replaces this direct bootstrap egress.
- The interactive operator runs Hermes' official `openai-codex` OAuth command
  inside the bootstrap container and chooses `gpt-5.5`. Credentials stay in
  the dedicated named volume; they are never printed, exported, copied into
  a repository file, `.env`, database, snapshot, audit record, or memory.
- The local-MVP runtime may consume this volume for the owner's Hermes
  dashboard/CLI after the dedicated runtime profile is bootstrapped. It has no
  VideoBox project/media/DB/API mount or route. Direct provider egress is a
  temporary local-MVP limitation, not a production allowlisted gateway.
- Hermes built-in memory and local Mem0 OSS are auxiliary context under Hermes
  runtime control. They do not change VideoBox project/editor/asset SSOT and
  do not authorize project-data transfer, mutation, render/export, CapCut, or
  an ordinary VideoBox API route.

## Rejected designs

1. Bind-mounting the host `~/.hermes` or reusing AK-System credentials would
   merge credential ownership across projects and is forbidden.
2. Changing the existing pre-auth service to allow networking would erase the
   static preflight boundary and is forbidden.
3. Attaching Hermes to `videobox-edge` or `videobox-internal` is forbidden,
   because those networks expose VideoBox services.
4. Implementing an OpenAI OAuth flow in VideoBox is forbidden. Hermes owns the
   official `openai-codex` device-code flow.

## Security and operational rules

- The auth volume is credential state, not VideoBox SSOT and not a backup.
- OAuth create, reuse, expiry, logout, and revoke are exercised only through
  official Hermes CLI behavior. Tests must prove no credential appears in
  logs, inspect output, configuration, or repository artifacts.
- Bootstrap requests include no project text, media, transcript, caption, or
  prompt. The later egress gateway also has no access to VideoBox data.
- The bootstrap command is interactive and user-operated. A successful login
  records only a redacted outcome and pinned Hermes image/model identifier.
- Any gateway, volume, or credential error fails closed. It cannot fall back to
  host credentials, a generic OpenAI API key, another provider, or an
  unrestricted network. The local-MVP direct egress is deliberately recorded
  as an unallowlisted limitation and must be replaced before production use.

## Acceptance criteria

1. Compose inspection proves pre-auth and OAuth volumes are different and
   Hermes has no VideoBox/host data mounts.
2. The OAuth profile attaches only to the dedicated egress network, never to
   `videobox-edge` or `videobox-internal`, and has no VideoBox data mount.
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

- VideoBox project-data transfer, editing mutation, rendering/export, CapCut
  or host bridge work, gateway API activation, MCP transport, consent UI,
  budgets, audit persistence, and capability issuer deployment.

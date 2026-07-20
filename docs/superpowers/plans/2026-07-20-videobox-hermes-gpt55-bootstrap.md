# VideoBox Hermes GPT-5.5 Bootstrap Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Give the local VideoBox stack a dedicated Hermes OAuth container where the owner can select openai-codex and gpt-5.5 without sharing host or AK-System state.

**Architecture:** Keep hermes-preauth unchanged. Add an independent hermes-oauth-bootstrap profile with one dedicated /opt/data volume and one egress-only Docker network; it has no VideoBox data/API/DB/host mount or host port. OAuth remains an owner-operated Hermes CLI interaction.

**Tech Stack:** Docker Compose, pinned Nous Hermes Agent image, pytest/PyYAML, PowerShell, official Hermes CLI.

---

### Task 1: Lock the OAuth bootstrap Compose contract

**Files:**
- Modify: tests/test_compose_contract.py
- Modify: compose.yaml

- [ ] Step 1: Write the failing contract test

~~~python
def test_hermes_oauth_bootstrap_is_isolated_from_preauth_and_videobox_data() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    bootstrap = compose["services"]["videobox-hermes-oauth-bootstrap"]
    assert bootstrap["profiles"] == ["hermes-oauth-bootstrap"]
    assert bootstrap["volumes"] == ["videobox_hermes_oauth_state:/opt/data"]
    assert bootstrap["networks"] == ["videobox-hermes-egress"]
    assert "ports" not in bootstrap
    assert "network_mode" not in bootstrap
    assert "videobox_hermes_preauth_state" not in str(bootstrap)
    assert "videobox-data" not in str(bootstrap)
    assert compose["networks"]["videobox-hermes-egress"] == {}
    assert "videobox_hermes_oauth_state" in compose["volumes"]
~~~

- [ ] Step 2: Run RED

Run: .\.venv\Scripts\python.exe -m pytest -q tests\test_compose_contract.py -k hermes_oauth_bootstrap

Expected: FAIL because the OAuth bootstrap service and volume do not exist.

- [ ] Step 3: Add the isolated profile

Add videobox-hermes-oauth-bootstrap with the same pinned image, read-only filesystem, tmpfs, capability limits, and logging contract as pre-auth:

~~~yaml
profiles: [hermes-oauth-bootstrap]
command: ["sleep", "infinity"]
volumes: [videobox_hermes_oauth_state:/opt/data]
networks: [videobox-hermes-egress]
~~~

Add an empty videobox-hermes-egress network and a videobox_hermes_oauth_state volume. Do not modify the existing pre-auth service.

- [ ] Step 4: Run GREEN

Run: .\.venv\Scripts\python.exe -m pytest -q tests\test_compose_contract.py

Expected: PASS.

- [ ] Step 5: Commit

~~~powershell
git add compose.yaml tests/test_compose_contract.py
git commit -m "feat: add isolated VideoBox Hermes OAuth profile"
~~~

### Task 2: Add owner bootstrap and runtime-verifier scripts

**Files:**
- Create: scripts/start-hermes-oauth-bootstrap.ps1
- Create: scripts/verify-hermes-oauth-bootstrap.ps1
- Create: tests/test_hermes_oauth_bootstrap_scripts.py

- [ ] Step 1: Write failing script-contract tests

~~~python
def test_oauth_bootstrap_scripts_use_only_the_dedicated_compose_profile() -> None:
    start = Path("scripts/start-hermes-oauth-bootstrap.ps1").read_text(encoding="utf-8")
    verify = Path("scripts/verify-hermes-oauth-bootstrap.ps1").read_text(encoding="utf-8")
    assert "hermes-oauth-bootstrap" in start
    assert "videobox-hermes-oauth-bootstrap" in start
    assert "hermes auth add openai-codex --type oauth" in start
    assert "gpt-5.5" in start
    assert "videobox_hermes_oauth_state" in verify
    assert "videobox_hermes_preauth_state" not in start
~~~

- [ ] Step 2: Run RED

Run: .\.venv\Scripts\python.exe -m pytest -q tests\test_hermes_oauth_bootstrap_scripts.py

Expected: FAIL because neither script exists.

- [ ] Step 3: Implement the scripts

The start script runs only:

~~~powershell
docker compose -p 65_videobox --profile hermes-oauth-bootstrap up -d videobox-hermes-oauth-bootstrap
docker compose -p 65_videobox exec -it videobox-hermes-oauth-bootstrap hermes auth add openai-codex --type oauth
docker compose -p 65_videobox exec -it videobox-hermes-oauth-bootstrap hermes model
~~~

The verifier uses Docker inspect to assert one /opt/data volume, no published port,
no videobox-edge/videobox-internal network, and the pinned image. It never reads
auth.json, prints environment values, invokes OAuth, or sends a GPT request.

- [ ] Step 4: Run GREEN

Run: .\.venv\Scripts\python.exe -m pytest -q tests\test_hermes_oauth_bootstrap_scripts.py

Expected: PASS.

- [ ] Step 5: Commit

~~~powershell
git add scripts/start-hermes-oauth-bootstrap.ps1 scripts/verify-hermes-oauth-bootstrap.ps1 tests/test_hermes_oauth_bootstrap_scripts.py
git commit -m "feat: add VideoBox Hermes OAuth bootstrap commands"
~~~

### Task 3: Perform owner OAuth and record redacted local evidence

**Files:**
- Modify: docs/development-status-2026-06-29.ko.md

- [ ] Step 1: Validate and start

Run:

~~~powershell
docker compose -p 65_videobox --profile hermes-oauth-bootstrap config
powershell -ExecutionPolicy Bypass -File scripts/start-hermes-oauth-bootstrap.ps1
~~~

Expected: the bootstrap service is running and no host port is published.

- [ ] Step 2: Complete interactive Hermes OAuth

The owner runs the two interactive commands printed by the start script, selects
openai-codex, and selects gpt-5.5. No device code, account identity, token, or
auth-file content is pasted into chat, logs, or repository files.

- [ ] Step 3: Verify and record limits

Run:

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-hermes-oauth-bootstrap.ps1
.\.venv\Scripts\python.exe -m pytest -q tests\test_compose_contract.py tests\test_hermes_oauth_bootstrap_scripts.py tests\test_hermes_capability_authority_contract.py
npm --prefix apps\web run build
git diff --check
~~~

Record only the profile name, pinned image, selected model, and success outcome.
Keep GPT inference/API routes, Telegram, mem0, egress gateway hardening, and
CapCut bridge pending.

- [ ] Step 4: Commit/push after review

~~~powershell
git add docs/development-status-2026-06-29.ko.md
git commit -m "docs: record VideoBox Hermes OAuth bootstrap evidence"
git push origin codex/videobox-container-compatibility
~~~

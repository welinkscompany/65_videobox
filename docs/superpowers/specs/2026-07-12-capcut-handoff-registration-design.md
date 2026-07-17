# CapCut Handoff Registration Design

## Decision

VideoBox keeps its exported real CapCut draft immutable and registers a separately copied CapCut project in the current Windows user's CapCut project root. Registration state belongs to the existing CapCut export's `metadata_json`; it is not a second export or job type.

## Alternatives considered

1. **Recommended: registered copy + export metadata.** The source draft remains recoverable, registration is idempotent by export ID, and no SQLite migration is needed.
2. Directly move the VideoBox draft into CapCut's project root. Rejected because it invalidates the artifact path VideoBox displays and breaks retry/recovery.
3. Require a manually configured project root only. Rejected because the verified Windows installation has a stable supported default and users need a meaningful failure/recovery path when it is unavailable.

## Contract

- Supported Windows root is `%LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft` and it is accepted only when a CapCut executable exists below `%LOCALAPPDATA%\\CapCut\\Apps` and the root is a writable directory.
- A registration copies the source draft directory to `<root>/videobox-<export_id>` through a unique temporary sibling and renames it only after copy success.
- A repeated registration reuses a complete existing directory only if it contains `draft_content.json`; an incomplete collision is removed before retry. Copy failure removes only the temporary destination and leaves the source untouched.
- The CapCut export metadata stores `handoff`: source URI, registered path, `ready|failed`, failure reason, and registration timestamp. It is returned by the existing CapCut export GET response.
- The UI offers registration only for a successful real draft export. It shows a Korean ready/error state, registered project path, and retry only after registration failure. Reload fetches the persisted state through the existing export GET call.

## Boundaries

- Registration does not launch CapCut, export an MP4, change CapCut settings, or upload/share data.
- Missing CapCut, missing root, non-writable root, and missing source draft are explicit errors with Korean recovery guidance.
- The real Desktop smoke validates registration from a newly generated `loop` draft, not a manually copied pre-existing QA directory.

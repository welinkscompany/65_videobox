"""The MCP server's default VideoBox API address must be the one that answers.

2026-09-28 (AK W1215-3): the default was `http://127.0.0.1:8000`, the API's
port *inside* the workspace container. The owner runs VideoBox as the
container stack every day, and that stack publishes exactly one host port --
the nginx front door at `127.0.0.1:${VIDEOBOX_WEB_PORT:-5173}`, which forwards
`/api/` to 8000 internally. Measured the same day: `GET /api/projects` on 5173
answered 200, on 8000 nothing listened. So an AK caller that relied on the
default reached nothing.

The test asserts a relation, not a literal: the default is whatever host port
`compose.yaml` publishes for the workspace, and the three places that carry a
default (the client dataclass, both server entry points, the start script)
agree with it.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _published_workspace_url() -> str:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    (mapping,) = compose["services"]["videobox-workspace"]["ports"]
    match = re.fullmatch(r"127\.0\.0\.1:\$\{VIDEOBOX_WEB_PORT:-(\d+)\}:\d+", mapping)
    assert match is not None, mapping
    return f"http://127.0.0.1:{match.group(1)}"


def test_api_client_default_is_the_container_front_door() -> None:
    from videobox_mcp.api_client import DEFAULT_API_BASE_URL, VideoBoxApiClient

    assert DEFAULT_API_BASE_URL == _published_workspace_url()
    assert VideoBoxApiClient().base_url == DEFAULT_API_BASE_URL


def test_server_entry_points_fall_back_to_the_same_default(monkeypatch) -> None:
    from videobox_mcp import server
    from videobox_mcp.api_client import DEFAULT_API_BASE_URL

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert '"http://127.0.0.1:8000"' not in source
    assert source.count('os.environ.get("VIDEOBOX_API_BASE_URL", DEFAULT_API_BASE_URL)') == 2
    assert DEFAULT_API_BASE_URL == _published_workspace_url()


def test_start_script_default_matches_the_client_default() -> None:
    from videobox_mcp.api_client import DEFAULT_API_BASE_URL

    script = (ROOT / "scripts" / "start-videobox-mcp-http.ps1").read_text(encoding="utf-8-sig")
    match = re.search(r'\[string\]\$VideoBoxApiBaseUrl\s*=\s*"([^"]+)"', script)
    assert match is not None
    assert match.group(1) == DEFAULT_API_BASE_URL

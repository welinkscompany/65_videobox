"""`scripts/set-local-model.ps1` -- 로컬 모델 이름을 한 번에 맞추는 도구.

owner가 새 qwen을 받을 때마다 모델 이름이 박힌 자리를 하나씩 손으로 고치다
빠뜨리는 사고를 막으려는 것이다(`tests/test_local_model_name_is_one_value.py`
docstring 참고). 이 시험은 스크립트를 **임시로 복사한 저장소** 위에서 돌려
실제 저장소 파일을 건드리지 않는다 -- `tests/test_start_hermes_yujin_script.py`,
`tests/test_owner_ready_script.py`가 쓰는 것과 같은 방식이다.
"""

from __future__ import annotations

import json
import socket
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "set-local-model.ps1"

# 스크립트가 고쳐야 한다고 주장하는 자리 전부. 실제 저장소에서 그대로 복사해
# 임시 저장소를 만든다.
RELATIVE_FILES = (
    ".env.container",
    "compose.hermes-yujin.yaml",
    # **2026-09-12에 더했다.** 같은 변수(`VIDEOBOX_LOCAL_MODEL_NAME`)의 기본값이
    # `compose.yaml`에도 커밋되어 있는데 스크립트도 이 하네스도 그 자리를
    # 빠뜨렸다. `.env.container`가 gitignore라 "커밋에 있는 자리"를 셋으로만 센
    # 탓이다 -- 그래서 새 모델로 바꿀 때 여기만 옛 `qwen3-35b`로 남았고, 대표님이
    # 그 모델을 삭제한 뒤에는 **없는 모델**을 가리키게 됐다.
    "compose.yaml",
    "config/hermes/yujin/config.yaml",
    "services/agent-gateway/src/videobox_agent_gateway/hermes_memory_adapter.py",
    "tests/test_hermes_yujin_compose_contract.py",
    "tests/test_hermes_yujin_profile_distribution.py",
    "tests/test_start_hermes_yujin_script.py",
)


def _copy_tree(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    scripts_dir = repository / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
    for relative in RELATIVE_FILES:
        source = ROOT / relative
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    return repository


def _unused_loopback_uri() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/"


@contextmanager
def _local_model_server(loaded_llm_keys: tuple[str, ...]) -> Iterator[str]:
    # LM Studio의 `/api/v1/models` 응답 모양을 흉내 낸다. `owner-ready.ps1`의
    # `Get-LocalModelCheck`가 실측(2026-08-11)한 것과 같은 모양이다 --
    # `type == "llm"`이고 `loaded_instances`가 비어 있지 않은 항목의 `key`만
    # "로드됨"으로 본다.
    models = [
        {"type": "llm", "key": key, "loaded_instances": [{"id": key}]}
        for key in loaded_llm_keys
    ]
    body = json.dumps({"models": models}).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _run(
    repository: Path,
    model_id: str,
    *,
    force: bool = False,
    local_model_uri: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repository / "scripts" / SCRIPT.name),
        model_id,
        "-RepositoryRoot",
        str(repository),
        "-LocalModelApiUri",
        local_model_uri or _unused_loopback_uri(),
    ]
    if force:
        command.append("-Force")
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def _read(repository: Path, relative: str) -> str:
    return (repository / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "bogus_model_id",
    (
        "",
        "not a model id",
        "../../etc/passwd",
        "model;rm -rf /",
        "model`whoami`",
        "$(whoami)",
        "model\nname",
        "a/b/c",
        "-startswithdash",
    ),
)
def test_rejects_a_bogus_model_id_without_touching_any_file(
    tmp_path: Path, bogus_model_id: str
) -> None:
    repository = _copy_tree(tmp_path)

    result = _run(repository, bogus_model_id, force=True)

    assert result.returncode != 0
    for relative in RELATIVE_FILES:
        assert _read(repository, relative) == (ROOT / relative).read_text(
            encoding="utf-8"
        ), f"{relative} 이 바뀌면 안 된다"


def test_accepts_a_plausible_org_slash_model_id_shape(tmp_path: Path) -> None:
    repository = _copy_tree(tmp_path)
    new_model = "qwen/qwen3.9-30b"

    result = _run(repository, new_model, force=True)

    assert result.returncode == 0, result.stderr


def test_refuses_a_model_that_is_not_loaded_without_force(tmp_path: Path) -> None:
    repository = _copy_tree(tmp_path)

    with _local_model_server(("some-other-loaded-model",)) as uri:
        result = _run(repository, "qwen/new-model-9b", local_model_uri=uri)

    assert result.returncode != 0
    combined_output = result.stdout + result.stderr
    # 지금 켜진 모델을 owner가 고를 수 있도록 실제로 보여줘야 한다.
    assert "some-other-loaded-model" in combined_output
    for relative in RELATIVE_FILES:
        assert _read(repository, relative) == (ROOT / relative).read_text(
            encoding="utf-8"
        ), f"{relative} 이 바뀌면 안 된다"


def test_refuses_when_lm_studio_is_unreachable_without_force(tmp_path: Path) -> None:
    repository = _copy_tree(tmp_path)

    result = _run(repository, "qwen/new-model-9b")

    assert result.returncode != 0
    for relative in RELATIVE_FILES:
        assert _read(repository, relative) == (ROOT / relative).read_text(
            encoding="utf-8"
        ), f"{relative} 이 바뀌면 안 된다"


def test_force_bypasses_the_loaded_model_check_entirely(tmp_path: Path) -> None:
    repository = _copy_tree(tmp_path)
    new_model = "qwen/new-model-9b"

    result = _run(repository, new_model, force=True)

    assert result.returncode == 0, result.stderr
    assert f"VIDEOBOX_LOCAL_MODEL_NAME={new_model}" in _read(
        repository, ".env.container"
    )


def test_changes_every_file_it_claims_to_when_the_model_is_loaded(
    tmp_path: Path,
) -> None:
    repository = _copy_tree(tmp_path)
    new_model = "qwen/new-model-9b"

    with _local_model_server((new_model,)) as uri:
        result = _run(repository, new_model, local_model_uri=uri)

    assert result.returncode == 0, result.stderr

    env_text = _read(repository, ".env.container")
    assert f"VIDEOBOX_LOCAL_MODEL_NAME={new_model}" in env_text

    nested_default = (
        "${VIDEOBOX_MEM0_LLM_MODEL:-${VIDEOBOX_LOCAL_MODEL_NAME:-"
        + new_model
        + "}}"
    )

    compose_text = _read(repository, "compose.hermes-yujin.yaml")
    assert nested_default in compose_text

    # `compose.yaml`의 커밋된 기본값. 새로 받은 환경은 `.env.container`가 없어
    # **이 값으로 뜬다** -- 여기만 안 바뀌면 유진이 없는 모델을 부른다.
    main_compose_text = _read(repository, "compose.yaml")
    assert f"VIDEOBOX_LOCAL_MODEL_NAME: ${{VIDEOBOX_LOCAL_MODEL_NAME:-{new_model}}}" in main_compose_text

    yujin_config_text = _read(repository, "config/hermes/yujin/config.yaml")
    assert f"name: {new_model}" in yujin_config_text

    adapter_text = _read(
        repository,
        "services/agent-gateway/src/videobox_agent_gateway/hermes_memory_adapter.py",
    )
    assert f'_LOCAL_MEM0_LLM_MODEL = "{new_model}"' in adapter_text

    compose_contract_text = _read(
        repository, "tests/test_hermes_yujin_compose_contract.py"
    )
    assert nested_default in compose_contract_text
    assert f'"name": "{new_model}"' in compose_contract_text

    profile_distribution_text = _read(
        repository, "tests/test_hermes_yujin_profile_distribution.py"
    )
    assert f'"name": "{new_model}"' in profile_distribution_text

    start_script_test_text = _read(
        repository, "tests/test_start_hermes_yujin_script.py"
    )
    assert f'"VIDEOBOX_MEM0_LLM_MODEL": "{new_model}",' in start_script_test_text


def test_creates_the_env_key_when_it_is_entirely_missing(tmp_path: Path) -> None:
    repository = _copy_tree(tmp_path)
    env_path = repository / ".env.container"
    filtered = "\n".join(
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("VIDEOBOX_LOCAL_MODEL_NAME=")
    )
    env_path.write_text(filtered + "\n", encoding="utf-8")
    new_model = "qwen/new-model-9b"

    result = _run(repository, new_model, force=True)

    assert result.returncode == 0, result.stderr
    assert f"VIDEOBOX_LOCAL_MODEL_NAME={new_model}" in _read(
        repository, ".env.container"
    )


def test_refuses_when_env_container_is_entirely_missing(tmp_path: Path) -> None:
    repository = _copy_tree(tmp_path)
    (repository / ".env.container").unlink()

    result = _run(repository, "qwen/new-model-9b", force=True)

    assert result.returncode != 0


def test_prints_the_next_step_command_in_korean(tmp_path: Path) -> None:
    repository = _copy_tree(tmp_path)
    new_model = "qwen/new-model-9b"

    result = _run(repository, new_model, force=True)

    assert result.returncode == 0, result.stderr
    assert "owner-ready.ps1" in result.stdout
    assert "-WithYujinMemory" in result.stdout

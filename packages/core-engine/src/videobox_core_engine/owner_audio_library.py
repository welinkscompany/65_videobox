"""Make the owner's own music and sound effects part of the searchable library.

The watcher moves a dropped file into a library folder. That alone does
nothing: `index_pending_library_audio` never walks a folder -- it reads
`list_assets_needing_audio_analysis`, whose query joins `media_packs` and
requires `active = 1 AND verified = 1`. A file that is not registered as a
library asset is therefore never measured and never findable, which the owner
experiences as "I added it and nothing happened".

So the moved file is registered here, through the same
`MediaLibraryStore.index_verified_pack` a real pack install uses. The owner's
files are simply their own pack: one stable `pack_id`, one stable `version`.
The version must stay fixed -- `index_verified_pack(active=True)` deactivates
every *other* version of the same pack_id, so a per-import version would make
each new drop hide the previous one.

Nothing here inspects the audio to decide music vs effect. The folder the file
arrived in decides that, per the owner's decision on 2026-08-10.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from videobox_core_engine.audio_descriptors import probe_duration_seconds
from videobox_core_engine.media_inbox import AUDIO_EXTENSIONS

_LOGGER = logging.getLogger(__name__)

#: One pack, one version, forever. See the module docstring for why the
#: version must not move.
OWNER_AUDIO_PACK_ID = "owner-audio"
OWNER_AUDIO_PACK_VERSION = "1"

#: `pack:` ids belong to installed packs; these files are not one, and
#: `project_asset_materializer` reads that prefix to record a source pack.
OWNER_AUDIO_ID_PREFIX = "owner"

#: Shown on the asset card. Plain words, no system vocabulary (§10.13).
OWNER_AUDIO_SOURCE = "직접 넣은 파일"

#: These files carry no external licence and no captured evidence, because
#: there is none: they are the owner's own material. Empty is the honest
#: record -- a URL or a timestamp here would assert a licence record that was
#: never obtained. The screen already renders an empty URL as
#: "라이선스 정보 없음" (`editorAssetProjection.ts:106`), and attribution is
#: not required because nobody has to credit themselves.
_NO_EXTERNAL_LICENCE: dict[str, Any] = {
    "official_url": "",
    "evidence_timestamp": "",
    "evidence_sha256": "",
    "attribution_required": False,
    "attribution_text": "",
}


class _OwnerAudioStore(Protocol):
    def list_pack_asset_digests(self, *, pack_id: str, version: str) -> dict[str, str]: ...
    def index_verified_pack(self, **kwargs: Any) -> None: ...


@dataclass(slots=True)
class OwnerAudioRegistrationReport:
    registered: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def owner_audio_library_asset_id(*, media_type: str, filename: str) -> str:
    return f"{OWNER_AUDIO_ID_PREFIX}:{media_type}:{filename}"


def register_owner_audio_library(
    *,
    store: _OwnerAudioStore,
    roots: Mapping[str, Path],
    install_path: Path,
    probe_duration: Callable[[Path], float] = probe_duration_seconds,
) -> OwnerAudioRegistrationReport:
    """Bring the library index level with what is on disk. Safe to repeat.

    `roots` maps a media type ("music", "sfx") to the folder holding files of
    that kind. Only files the index has never seen are read: this runs on the
    same background pass as the audio indexer, and hashing the owner's whole
    music collection every minute would be a large invisible cost for a pass
    that almost always has nothing to do.

    A file already registered under the same name is left alone. The library
    folder is written only by the watcher, which gives a differing file a
    hash-suffixed name rather than reusing one, so one name there means one
    set of bytes.
    """
    report = OwnerAudioRegistrationReport()
    already_indexed = store.list_pack_asset_digests(
        pack_id=OWNER_AUDIO_PACK_ID, version=OWNER_AUDIO_PACK_VERSION
    )
    new_assets: list[dict[str, Any]] = []
    for media_type, root in sorted(roots.items()):
        if not Path(root).is_dir():
            continue
        for path in sorted(Path(root).iterdir()):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            library_asset_id = owner_audio_library_asset_id(
                media_type=media_type, filename=path.name
            )
            if library_asset_id in already_indexed:
                continue
            try:
                digest = _sha256_file(path)
                duration = float(probe_duration(path))
            except (OSError, ValueError):
                # 재지 못한 파일은 보고서에 남긴다. 조용히 건너뛰면 owner는
                # 넣은 파일이 왜 안 보이는지 알 방법이 없다.
                report.failed.append(library_asset_id)
                continue
            new_assets.append({
                "library_asset_id": library_asset_id,
                # 화면이 이름표가 없을 때 대신 보여 주는 값이라, owner가 붙인
                # 파일 이름이 그대로 보이는 편이 낫다.
                "asset_id": path.stem,
                "media_type": media_type,
                "duration_seconds": duration,
                "sha256": digest,
                "path": path,
                "source": OWNER_AUDIO_SOURCE,
                "creator": "",
                "license": dict(_NO_EXTERNAL_LICENCE),
                "tags": [],
            })

    if not new_assets:
        return report

    store.index_verified_pack(
        pack_id=OWNER_AUDIO_PACK_ID,
        version=OWNER_AUDIO_PACK_VERSION,
        install_path=install_path,
        assets=new_assets,
        active=True,
    )
    report.registered = [str(asset["library_asset_id"]) for asset in new_assets]
    _LOGGER.info("직접 넣은 소리 %d개를 라이브러리에 넣었습니다.", len(report.registered))
    return report


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

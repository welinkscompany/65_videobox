from __future__ import annotations

import copy

import pytest

from videobox_domain_models.media_pack import MediaPackAsset, MediaPackManifest


def valid_manifest() -> dict[str, object]:
    return {
        "pack_id": "starter-001",
        "version": "1.0.0",
        "declared_bytes": 314_572_800,
        "sha256": "a" * 64,
        "assets": [
            {
                "asset_id": "music-001",
                "pack_path": "assets/music-001.mp3",
                "sha256": "b" * 64,
                "media_type": "music",
                "duration_seconds": 120.5,
                "source": "Example Audio Archive",
                "creator": "Example Creator",
                "license": {
                    "official_url": "https://example.com/license",
                    "commercial_use": True,
                    "redistribution": True,
                    "evidence_timestamp": "2026-07-12T10:00:00Z",
                    "evidence_sha256": "c" * 64,
                },
            }
        ],
    }


def test_manifest_rejects_asset_without_redistribution_right() -> None:
    with pytest.raises(ValueError, match="redistribution"):
        MediaPackAsset.from_dict(
            {"license": {"commercial_use": True, "redistribution": False}},
            pack_id="starter-001",
        )


def test_manifest_requires_namespaced_unique_ids_and_sha256() -> None:
    manifest = MediaPackManifest.from_dict(valid_manifest())

    assert manifest.assets[0].library_asset_id == "pack:starter-001:music-001"


def test_manifest_carries_canonical_tags_and_required_attribution_metadata() -> None:
    data = valid_manifest()
    asset = data["assets"][0]
    assert isinstance(asset, dict)
    asset["tags"] = ["calm", "business"]
    license_data = asset["license"]
    assert isinstance(license_data, dict)
    license_data.update({"attribution_required": True, "attribution_text": "Music by Example Creator"})

    parsed = MediaPackManifest.from_dict(data).assets[0]

    assert parsed.tags == ("calm", "business")
    assert parsed.license.attribution_required is True
    assert parsed.license.attribution_text == "Music by Example Creator"


@pytest.mark.parametrize("pack_path", ["/absolute.mp3", "../escape.mp3", "assets/../escape.mp3", "C:/escape.mp3", r"C:\escape.mp3", "//server/share.mp3"])
def test_manifest_rejects_unsafe_asset_pack_path(pack_path: str) -> None:
    data = valid_manifest()
    asset = data["assets"][0]
    assert isinstance(asset, dict)
    asset["pack_path"] = pack_path

    with pytest.raises(ValueError, match="pack_path"):
        MediaPackManifest.from_dict(data)


@pytest.mark.parametrize("commercial_use", [False, "unknown", 1])
def test_manifest_rejects_unknown_or_invalid_commercial_use(
    commercial_use: object,
) -> None:
    asset = valid_manifest()["assets"][0]
    assert isinstance(asset, dict)
    license_data = asset["license"]
    assert isinstance(license_data, dict)
    license_data["commercial_use"] = commercial_use

    with pytest.raises(ValueError, match="commercial_use"):
        MediaPackAsset.from_dict(asset, pack_id="starter-001")


def test_manifest_rejects_duplicate_asset_ids() -> None:
    data = valid_manifest()
    assets = data["assets"]
    assert isinstance(assets, list)
    assets.append(copy.deepcopy(assets[0]))

    with pytest.raises(ValueError, match="unique"):
        MediaPackManifest.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "1.0"),
        ("sha256", "not-a-sha256"),
        ("declared_bytes", 0),
    ],
)
def test_manifest_rejects_invalid_pack_metadata(field: str, value: object) -> None:
    data = valid_manifest()
    data[field] = value

    with pytest.raises(ValueError):
        MediaPackManifest.from_dict(data)


def test_manifest_rejects_semver_prerelease_numeric_identifier_with_leading_zero() -> None:
    data = valid_manifest()
    data["version"] = "1.0.0-01"

    with pytest.raises(ValueError, match="semantic version"):
        MediaPackManifest.from_dict(data)


def test_manifest_rejects_unicode_semver_numeric_identifier() -> None:
    data = valid_manifest()
    data["version"] = "1.0.0-1١"

    with pytest.raises(ValueError, match="semantic version"):
        MediaPackManifest.from_dict(data)


@pytest.mark.parametrize("declared_bytes", [300 * 1024**2, 500 * 1024**2])
def test_manifest_accepts_declared_bytes_at_mib_boundaries(
    declared_bytes: int,
) -> None:
    data = valid_manifest()
    data["declared_bytes"] = declared_bytes

    assert MediaPackManifest.from_dict(data).declared_bytes == declared_bytes


@pytest.mark.parametrize("declared_bytes", [299 * 1024**2, 501 * 1024**2])
def test_manifest_rejects_declared_bytes_outside_mib_boundaries(
    declared_bytes: int,
) -> None:
    data = valid_manifest()
    data["declared_bytes"] = declared_bytes

    with pytest.raises(ValueError, match="declared_bytes"):
        MediaPackManifest.from_dict(data)


def test_asset_requires_declared_pack_id_context() -> None:
    asset = valid_manifest()["assets"][0]

    with pytest.raises(ValueError, match="pack_id"):
        MediaPackAsset.from_dict(asset)


@pytest.mark.parametrize("pack_id", ["", "pack:starter-001"])
def test_asset_rejects_invalid_declared_pack_id_context(pack_id: str) -> None:
    asset = valid_manifest()["assets"][0]

    with pytest.raises(ValueError, match="pack_id"):
        MediaPackAsset.from_dict(asset, pack_id=pack_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset_id", "music:001"),
        ("sha256", "not-a-sha256"),
        ("media_type", "video"),
        ("duration_seconds", 0),
        ("duration_seconds", float("nan")),
        ("duration_seconds", float("inf")),
        ("source", " "),
        ("creator", " "),
    ],
)
def test_asset_rejects_invalid_required_fields(field: str, value: object) -> None:
    data = valid_manifest()
    asset = data["assets"][0]
    assert isinstance(asset, dict)
    asset[field] = value

    with pytest.raises(ValueError, match=field):
        MediaPackManifest.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("official_url", "ftp://example.com/license"),
        ("evidence_timestamp", "2026-07-12T10:00:00"),
        ("redistribution", "unknown"),
        ("redistribution", 1),
    ],
)
def test_asset_rejects_invalid_license_terms(field: str, value: object) -> None:
    data = valid_manifest()
    asset = data["assets"][0]
    assert isinstance(asset, dict)
    license_data = asset["license"]
    assert isinstance(license_data, dict)
    license_data[field] = value

    with pytest.raises(ValueError, match=field):
        MediaPackManifest.from_dict(data)


def test_manifest_rejects_missing_official_license_evidence() -> None:
    data = valid_manifest()
    asset = data["assets"][0]
    assert isinstance(asset, dict)
    license_data = asset["license"]
    assert isinstance(license_data, dict)
    del license_data["evidence_sha256"]

    with pytest.raises(ValueError, match="evidence_sha256"):
        MediaPackManifest.from_dict(data)

from __future__ import annotations

import re
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml


SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "oauth",
    "clientsecret",
    "mem0",
)
FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r"[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]", re.I),
    re.compile(r"/(?:home|users)/", re.I),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}\b", re.I),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,255}\b", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,255}\b", re.I),
    re.compile(r"\bbearer +[A-Za-z0-9._~+/-]{16,255}={0,2}\b", re.I),
    re.compile(
        r"\b(?:api[\s_-]*key|oauth(?:[\s_-]*(?:token|access|refresh))?|"
        r"access[\s_-]*token|refresh[\s_-]*token|password|passwd|"
        r"mem0(?:[\s_-]*(?:api[\s_-]*key|token|credential))?)\b"
        r"\s*[:=]\s*[\"']?[^\s\"'#]{4,}",
        re.I | re.M,
    ),
)
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


class UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(
        self,
        node: yaml.nodes.MappingNode,
        deep: bool = False,
    ) -> dict[Any, Any]:
        if not isinstance(node, yaml.nodes.MappingNode):
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "expected a mapping node",
                node.start_mark,
            )
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as error:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found an unhashable key",
                    key_node.start_mark,
                ) from error
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found a duplicate key",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _decode_text(path: Path) -> str:
    payload = path.read_bytes()
    if payload.startswith(ZIP_MAGICS):
        raise ValueError("archive payload")
    if payload.startswith((b"MZ", b"\x7fELF")):
        raise ValueError("executable payload")
    text = payload.decode("utf-8-sig", errors="strict")
    for character in text:
        if character not in "\t\n\r" and unicodedata.category(character) == "Cc":
            raise ValueError("disallowed control character")
    if text.startswith("#!"):
        raise ValueError("executable text payload")
    return text


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _assert_safe_yaml_tree(value: Any, seen: set[int]) -> None:
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for key, child in value.items():
            if _is_sensitive_key(key):
                raise ValueError("sensitive YAML key")
            _assert_safe_yaml_tree(child, seen)
        return
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for child in value:
            _assert_safe_yaml_tree(child, seen)


def verify_profile_content(profile_root: Path) -> None:
    for path in sorted(profile_root.rglob("*")):
        if not path.is_file():
            continue
        text = _decode_text(path)
        if any(pattern.search(text) for pattern in FORBIDDEN_TEXT_PATTERNS):
            raise ValueError("forbidden text material")
        if path.suffix.lower() in {".yaml", ".yml"}:
            parsed = yaml.load(text, Loader=UniqueKeySafeLoader)
            _assert_safe_yaml_tree(parsed, set())


def main() -> int:
    try:
        if len(sys.argv) != 2:
            return 2
        profile_root = Path(sys.argv[1]).resolve(strict=True)
        if not profile_root.is_dir():
            return 1
        verify_profile_content(profile_root)
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

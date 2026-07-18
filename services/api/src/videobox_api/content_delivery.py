from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

_INLINE_MEDIA_TYPES = {
    "audio/aac", "audio/flac", "audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav", "audio/webm",
    "image/jpeg", "image/png", "video/mp4", "video/ogg", "video/webm",
}
_SAFE_MEDIA_TYPE_ALIASES = {
    "audio/x-flac": "audio/flac",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
}


def deliver_file(*, request: Request, path: Path, media_type: str | None = None) -> Response:
    """Return a local project file, honoring one RFC 7233 byte range."""
    requested_type = (media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream").lower()
    requested_type = _SAFE_MEDIA_TYPE_ALIASES.get(requested_type, requested_type)
    inline = requested_type in _INLINE_MEDIA_TYPES
    resolved_type = requested_type if inline else "application/octet-stream"
    headers = {"Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
    if not inline:
        headers["Content-Disposition"] = "attachment; filename=download"
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=resolved_type, headers=headers)

    size = path.stat().st_size
    parsed = _parse_single_range(range_header, size)
    if parsed is None:
        return Response(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, headers={**headers, "Content-Range": f"bytes */{size}"})
    start, end = parsed
    length = end - start + 1
    return StreamingResponse(
        _read_range(path, start, length),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=resolved_type,
        headers={**headers, "Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(length)},
    )


def _parse_single_range(value: str, size: int) -> tuple[int, int] | None:
    if size <= 0 or not value.startswith("bytes=") or "," in value:
        return None
    start_text, separator, end_text = value.removeprefix("bytes=").strip().partition("-")
    if not separator:
        return None
    try:
        if start_text:
            start = int(start_text)
            end = size - 1 if not end_text else int(end_text)
        elif end_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                return None
            start = max(size - suffix_length, 0)
            end = size - 1
        else:
            return None
    except ValueError:
        return None
    if start < 0 or end < start or start >= size:
        return None
    return start, min(end, size - 1)


def _read_range(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk

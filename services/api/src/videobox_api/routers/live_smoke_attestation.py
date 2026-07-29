from __future__ import annotations

from hashlib import sha256
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Query, status

from videobox_storage.local_project_store import LocalProjectStore


_REQUEST_DOMAIN = "videobox-live-smoke-root-attestation-request-v1"
_RESPONSE_DOMAIN = "videobox-live-smoke-root-attestation-response-v1"


def _mac(secret: bytes, message: str) -> str:
    return hmac.new(secret, message.encode("utf-8"), sha256).hexdigest()


def build_live_smoke_attestation_router(
    store: LocalProjectStore,
    *,
    secret: bytes,
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/internal/live-smoke/projects/{project_id}/root-attestation",
    )
    def attest_project_root(
        project_id: str,
        nonce: str = Query(pattern=r"^[0-9a-f]{64}$"),
        request_attestation: str | None = Header(
            default=None,
            alias="X-VideoBox-Live-Smoke-Attestation",
        ),
    ) -> dict[str, str]:
        expected_request = _mac(
            secret,
            f"{_REQUEST_DOMAIN}\0{project_id}\0{nonce}",
        )
        if (
            request_attestation is None
            or not hmac.compare_digest(request_attestation, expected_request)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="not_found",
            )
        try:
            store.get_project(project_id=project_id)
            project_root = store.project_root(project_id).resolve(strict=True)
        except (KeyError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="not_found",
            ) from exc
        canonical_root = os.path.normcase(str(project_root))
        return {
            "version": "v1",
            "project_id": project_id,
            "nonce": nonce,
            "root_attestation": _mac(
                secret,
                (
                    f"{_RESPONSE_DOMAIN}\0{project_id}\0{nonce}"
                    f"\0{canonical_root}"
                ),
            ),
        }

    return router

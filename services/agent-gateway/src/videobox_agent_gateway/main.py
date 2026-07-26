"""Health-only A1 surface for the isolated VideoBox agent gateway."""

from fastapi import FastAPI


app = FastAPI(
    title="VideoBox Agent Gateway",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
def health() -> dict[str, bool | str]:
    """Report only this HTTP process's readiness.

    Hermes transport, provider access, and chat are intentionally deferred.
    """

    return {
        "status": "ready",
        "scope": "gateway_http_process",
        "hermes_http_ready": False,
        "provider_ready": False,
        "chat_ready": False,
    }

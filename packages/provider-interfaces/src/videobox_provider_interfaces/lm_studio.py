from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from videobox_provider_interfaces.embeddings import EmbeddingRequest, EmbeddingResponse, EmbeddingProvider
from videobox_provider_interfaces.vision import FIXED_VISION_LAYERS, FIXED_VISION_RESPONSE_SCHEMA, VisionAnalysisRequest, VisionAnalysisResponse, VisionProvider


_LM_STUDIO_URL = "http://127.0.0.1:1234/v1"
_MAX_IMAGES = 6
_MAX_ENCODED_IMAGE_BYTES = int(1.5 * 1024 * 1024)
_VISION_SCHEMA_KEYS = frozenset({"layers", "summary", "confidence", "review_reasons"})


@dataclass(slots=True, frozen=True)
class LMStudioProviderError(Exception):
    message: str
    code: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True, frozen=True)
class LMStudioCapabilityProfile:
    vision_model_name: str | None
    text_model_name: str | None
    embedding_model_name: str | None
    structured_json: bool


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        raise HTTPError(req.full_url, code, "LM Studio redirects are forbidden", headers, fp)


@dataclass(slots=True)
class LMStudioHTTPTransport:
    base_url: str = _LM_STUDIO_URL
    http_client: Callable[..., Any] | None = None
    requested_endpoints: list[str] = field(default_factory=list, init=False)

    def _validate_endpoint(self) -> None:
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != 1234
            or parsed.path != "/v1"
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise LMStudioProviderError("LM Studio endpoint must be exact loopback http://127.0.0.1:1234/v1.", "blocked")

    def capability_profile(self, *, timeout_seconds: int = 15) -> LMStudioCapabilityProfile:
        payload = self.request_json("/models", None, timeout_seconds=timeout_seconds)
        models = payload.get("data")
        if not isinstance(models, list):
            raise LMStudioProviderError("LM Studio returned malformed model state.", "failed")
        selected: dict[str, str | None] = {"vision": None, "text": None, "embedding": None}
        structured_json = False
        for model in models:
            if not isinstance(model, dict) or model.get("loaded") is not True or not isinstance(model.get("id"), str):
                continue
            # Do not infer execution privileges from server-controlled generic metadata.
            native = model.get("native_capabilities")
            if not isinstance(native, list):
                continue
            capabilities = {str(value).lower() for value in native}
            if selected["vision"] is None and {"vision", "structured_json"} <= capabilities:
                selected["vision"] = model["id"]
            if selected["text"] is None and {"text", "structured_json"} <= capabilities:
                selected["text"] = model["id"]
            if selected["embedding"] is None and "embedding" in capabilities:
                selected["embedding"] = model["id"]
            if "structured_json" in capabilities:
                structured_json = True
        return LMStudioCapabilityProfile(
            vision_model_name=selected["vision"],
            text_model_name=selected["text"],
            embedding_model_name=selected["embedding"],
            structured_json=structured_json,
        )

    def preflight(self, *, model_name: str, capability: str, timeout_seconds: int = 15) -> str:
        payload = self.request_json("/models", None, timeout_seconds=timeout_seconds)
        models = payload.get("data")
        if not isinstance(models, list):
            raise LMStudioProviderError("LM Studio returned malformed model state.", "failed")
        model = next((item for item in models if isinstance(item, dict) and item.get("id") == model_name), None)
        if model is None or model.get("loaded") is not True:
            raise LMStudioProviderError("Requested local model is unavailable or unloaded.", "blocked")
        native = model.get("native_capabilities")
        if not isinstance(native, list):
            raise LMStudioProviderError(f"Loaded model does not support {capability}.", "blocked")
        capabilities = {str(value).lower() for value in native}
        if capability not in capabilities or (capability == "vision" and "structured_json" not in capabilities):
            raise LMStudioProviderError(f"Loaded model does not support {capability}.", "blocked")
        return capability

    def request_json(self, path: str, payload: dict[str, Any] | None, *, timeout_seconds: int) -> dict[str, Any]:
        self._validate_endpoint()  # Revalidate immediately before every outbound operation.
        endpoint = f"{self.base_url}{path}"
        self.requested_endpoints.append(endpoint)
        request = Request(
            endpoint,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            if self.http_client is not None:
                response = self.http_client(request, timeout=timeout_seconds, allow_redirects=False)
            else:
                response = build_opener(_NoRedirect()).open(request, timeout=timeout_seconds)
            with response:
                decoded = json.loads(response.read().decode("utf-8"))
        except LMStudioProviderError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise LMStudioProviderError("LM Studio local resource is unavailable.", "blocked") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LMStudioProviderError("LM Studio returned malformed JSON.", "failed") from exc
        if not isinstance(decoded, dict):
            raise LMStudioProviderError("LM Studio response must be a JSON object.", "failed")
        return decoded


@dataclass(slots=True)
class LMStudioVisionProvider(VisionProvider):
    transport: LMStudioHTTPTransport
    provider_name: str = "lm_studio"
    timeout_seconds: int = 120

    def analyze_images(self, request: VisionAnalysisRequest) -> VisionAnalysisResponse:
        self.transport.preflight(model_name=request.model_name, capability="vision", timeout_seconds=self.timeout_seconds)
        images = tuple(self._prepare_image(image) for image in request.images[:_MAX_IMAGES])
        if not images:
            raise LMStudioProviderError("Vision analysis requires at least one image.", "failed")
        content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        content.extend({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")}} for image in images)
        payload = self.transport.request_json("/chat/completions", {"model": request.model_name, "messages": [{"role": "user", "content": content}], "response_format": {"type": "json_schema", "json_schema": {"name": "videobox_vision", "strict": True, "schema": FIXED_VISION_RESPONSE_SCHEMA}}}, timeout_seconds=self.timeout_seconds)
        output = self._parse_output(payload)
        return VisionAnalysisResponse(provider_name=self.provider_name, model_name=request.model_name, output_data=output)

    def _prepare_image(self, image: bytes) -> bytes:
        if not isinstance(image, bytes) or not image:
            raise LMStudioProviderError("Vision image must be non-empty bytes.", "failed")
        prepared = image
        try:
            from PIL import Image
            from io import BytesIO
            with Image.open(BytesIO(image)) as source:
                source.thumbnail((768, 768))
                buffer = BytesIO()
                source.convert("RGB").save(buffer, format="JPEG", quality=85, optimize=True)
                prepared = buffer.getvalue()
        except ImportError as exc:
            raise LMStudioProviderError("Vision image decoder is unavailable.", "blocked") from exc
        except Exception as exc:
            raise LMStudioProviderError("Vision image must be decodable image bytes.", "failed") from exc
        if len(prepared) > _MAX_ENCODED_IMAGE_BYTES:
            raise LMStudioProviderError("Prepared vision image exceeds 1.5 MiB.", "failed")
        return prepared

    def _parse_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = payload["choices"][0]["message"]["content"]
            output = json.loads(raw)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LMStudioProviderError("Vision response is malformed JSON.", "failed") from exc
        if not isinstance(output, dict) or set(output) != _VISION_SCHEMA_KEYS or not isinstance(output["layers"], dict) or set(output["layers"]) != set(FIXED_VISION_LAYERS) or not all(isinstance(output["layers"][layer], list) and all(isinstance(item, str) for item in output["layers"][layer]) for layer in FIXED_VISION_LAYERS) or not isinstance(output["summary"], str) or not isinstance(output["confidence"], (int, float)) or isinstance(output["confidence"], bool) or not math.isfinite(output["confidence"]) or not isinstance(output["review_reasons"], list) or not all(isinstance(reason, str) for reason in output["review_reasons"]):
            raise LMStudioProviderError("Vision response violates the fixed schema.", "failed")
        return output


@dataclass(slots=True)
class LMStudioEmbeddingProvider(EmbeddingProvider):
    transport: LMStudioHTTPTransport
    provider_name: str = "lm_studio"
    timeout_seconds: int = 15

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.transport.preflight(model_name=request.model_name, capability="embedding", timeout_seconds=self.timeout_seconds)
        if not request.inputs or not all(isinstance(value, str) and value for value in request.inputs):
            raise LMStudioProviderError("Embedding input must contain non-empty strings.", "failed")
        payload = self.transport.request_json("/embeddings", {"model": request.model_name, "input": list(request.inputs)}, timeout_seconds=self.timeout_seconds)
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(request.inputs):
            raise LMStudioProviderError("Embedding response is malformed.", "failed")
        try:
            vectors = tuple(tuple(float(value) for value in item["embedding"]) for item in data)
        except (KeyError, TypeError, ValueError) as exc:
            raise LMStudioProviderError("Embedding response is malformed.", "failed") from exc
        if not all(vector and all(math.isfinite(value) for value in vector) for vector in vectors):
            raise LMStudioProviderError("Embedding response must contain finite non-empty vectors.", "failed")
        return EmbeddingResponse(provider_name=self.provider_name, model_name=request.model_name, vectors=vectors)

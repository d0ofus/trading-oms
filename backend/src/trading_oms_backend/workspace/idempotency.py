import hashlib
import json
import re

from fastapi.responses import JSONResponse, Response

from .store import now


async def execute_once(request, call_next, store):
    key = request.headers.get("x-idempotency-key")
    if (
        not key
        or request.method not in {"POST", "PUT", "DELETE"}
        or request.url.path == "/api/auth/pair"
    ):
        return await call_next(request)
    if not re.fullmatch(r"[a-f0-9-]{32,36}", key):
        return JSONResponse({"detail": "Invalid action identity."}, status_code=422)
    # Persist only a one-way digest, never request bodies containing credentials.
    payload_hash = hashlib.sha256(
        request.method.encode()
        + str(request.url.path).encode()
        + str(request.url.query).encode()
        + await request.body()
    ).hexdigest()
    with store.transaction() as db:
        prior = store.read(db, "http_mutation", key)
        if prior:
            if prior["hash"] != payload_hash:
                return JSONResponse(
                    {"detail": "This action identity belongs to a different request."},
                    status_code=409,
                )
            if prior["state"] != "completed":
                return JSONResponse(
                    {"detail": "Action pending or uncertain. Inspect its current state."},
                    status_code=409,
                )
            return JSONResponse(prior["response"], status_code=prior["status"])
        store.write(
            db, "http_mutation", key, {"hash": payload_hash, "state": "pending", "timestamp": now()}
        )
    response = await call_next(request)
    content = b"".join([part async for part in response.body_iterator])
    if response.status_code < 500:
        store.put(
            "http_mutation",
            key,
            {
                "hash": payload_hash,
                "state": "completed",
                "status": response.status_code,
                "response": json.loads(content),
            },
        )
    return Response(
        content,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type="application/json",
    )

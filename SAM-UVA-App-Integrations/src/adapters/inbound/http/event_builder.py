"""
event_builder — translate an inbound HTTP request into the lambda-proxy ``event``
dict the legacy-shaped use cases expect, and translate their lambda-proxy
response back into an HTTP response.

The hexagonal core use cases were preserved with their original API Gateway
"lambda-proxy" contract (they read ``event['pathParameters']`` /
``event['queryStringParameters']`` / ``event['body']`` and return
``{"statusCode", "body", "headers"?}``). This adapter is the single seam that
lets the FastAPI inbound adapter reuse those exact use cases unchanged, so the
HTTP behaviour stays identical to the old one-Lambda-per-endpoint deployment.

Exceptions raised by the use cases are intentionally allowed to propagate; the
app-level ``@app.exception_handler(Exception)`` maps them to a 502 (API Gateway
parity).
"""

import json

from fastapi import Request
from fastapi.responses import JSONResponse


async def build_event(request: Request, path_parameters: dict) -> dict:
    """Build an API-Gateway-proxy-like event from a FastAPI request."""
    qs = dict(request.query_params)
    raw_body = await request.body()
    body = raw_body.decode("utf-8") if raw_body else None
    return {
        "pathParameters": path_parameters or {},
        # Mirror API Gateway: no query string -> None (use cases handle `or {}`).
        "queryStringParameters": qs or None,
        "httpMethod": request.method,
        "body": body,
    }


def to_response(proxy_result: dict) -> JSONResponse:
    """
    Translate a lambda-proxy ``{"statusCode", "body", "headers"?}`` dict into a
    JSONResponse, preserving the exact status code, the JSON-string body (parsed
    so the wire shape matches the legacy API Gateway proxy integration), and any
    headers the use case set (e.g. Content-Type: application/json).
    """
    status_code = proxy_result["statusCode"]
    body = proxy_result.get("body", "null")
    headers = proxy_result.get("headers")
    try:
        parsed = json.loads(body) if isinstance(body, str) else body
    except (TypeError, ValueError):
        parsed = body
    return JSONResponse(status_code=status_code, content=parsed, headers=headers)

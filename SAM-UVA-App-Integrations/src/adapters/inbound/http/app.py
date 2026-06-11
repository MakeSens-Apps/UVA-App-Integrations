"""
app — FastAPI application factory for the single HTTP Lambda.

This ``app`` is wrapped by Mangum in ``src/lambda_handlers/api_handler.py`` and
serves ALL HTTP endpoints of the UVA-App-Integrations microservice (previously
one Lambda per endpoint: UVALastConnection for GET /{id_uva}/connection and
CreateRacimo for POST /CreateRacimo). The non-HTTP integrations (DynamoDB
Stream -> Lambda for DeviceDataAccess and Cloud) stay as separate Lambdas that
share this same build.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.adapters.inbound.http.routes import router

app = FastAPI(
    title="UVA-App-Integrations API",
    description="Single HTTP Lambda (FastAPI + Mangum) for the UVA-App-Integrations microservice.",
    version="2.0",
)

app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Map any uncaught use-case exception to a JSON 502, mirroring the legacy
    API-Gateway-proxy behaviour: when the per-endpoint Lambda raised (e.g. the
    known ``last_connection`` bug where AppSync ``getUVA`` returns ``null`` and
    the handler does ``None.get('createdAt')`` -> AttributeError), API Gateway
    returned an HTTP 502 with a JSON body. The e2e suite of THIS repo asserts that
    exact status (502) on those backend-error cases
    (``test/e2e/test_last_connection_e2e.py::TestRedCases``), so we preserve it
    here instead of letting Mangum emit a bare text/plain 500.

    The 200 envelopes produced by the use cases (and any 404/4xx the FastAPI
    router itself returns for unmatched routes/methods) are returned normally and
    are unaffected by this handler.
    """
    return JSONResponse(
        status_code=502,
        content={"message": "Internal server error"},
    )

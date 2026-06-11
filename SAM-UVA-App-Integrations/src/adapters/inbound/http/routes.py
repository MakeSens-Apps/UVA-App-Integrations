"""
routes — FastAPI routes for the single HTTP Lambda.

Each route is a thin inbound adapter: it builds a lambda-proxy event, invokes the
corresponding core use case (unchanged), and translates the use case's
``{"statusCode", "body"}`` result back into an HTTP response. Uncaught exceptions
from a use case are allowed to propagate so the app-level exception handler
returns 502 — identical to the legacy API-Gateway-proxy behaviour the e2e tests
assert.

Paths and methods are preserved exactly:
    GET  /{id_uva}/connection
    POST /CreateRacimo

The literal ``/CreateRacimo`` route is declared before the parametrized
``/{id_uva}/connection`` route so the literal path is matched first and is never
captured by the ``{id_uva}`` path parameter.
"""

from fastapi import APIRouter, Request

from src.adapters.inbound.http.event_builder import build_event, to_response
from src.core.use_cases.last_connection import lambda_handler as last_connection_handler
from src.core.use_cases.create_racimo import lambda_handler as create_racimo_handler

router = APIRouter()


@router.post("/CreateRacimo")
async def create_racimo(request: Request):
    event = await build_event(request, path_parameters={})
    result = create_racimo_handler(event, None)
    return to_response(result)


@router.get("/{id_uva}/connection")
async def get_last_connection(id_uva: str, request: Request):
    event = await build_event(request, path_parameters={"id_uva": id_uva})
    result = last_connection_handler(event, None)
    return to_response(result)

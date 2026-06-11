"""
api_handler — the ONE and ONLY HTTP Lambda entrypoint.

Mangum adapts the FastAPI ASGI app to the AWS Lambda + API Gateway event model.
This single function serves every HTTP route (GET /{id_uva}/connection and
POST /CreateRacimo), replacing the previous one-Lambda-per-endpoint layout
(UVALastConnection + CreateRacimo).
"""

from lambda_handlers import _bootstrap  # noqa: F401  -- makes `src` importable

from mangum import Mangum

from src.adapters.inbound.http.app import app

handler = Mangum(app)

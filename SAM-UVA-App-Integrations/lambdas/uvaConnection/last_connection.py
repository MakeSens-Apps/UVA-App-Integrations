"""
last_connection.py — LEGACY lambda-proxy shim (inbound adapter).

After the hexagonal migration the REAL logic for GET /{id_uva}/connection lives
in ``src/core/use_cases/last_connection.py``. This module is kept at its exact
legacy path/name with the exact ``lambda_handler(event, context)`` signature (and
the helper functions) so the existing integration tests — which do
``import last_connection`` / ``from last_connection import lambda_handler`` and
call the handler directly, then ``patch.object(last_connection.requests, "post")``
— keep passing WITHOUT modification. Behaviour (status codes, body shape, and the
uncaught-exception 5xx branches such as the ``getUVA: null`` -> AttributeError
bug) is byte-for-byte identical.

The deployed single HTTP Lambda no longer routes through this module — it serves
GET /{id_uva}/connection via the FastAPI app (see src/adapters/inbound/http).
This shim is the integration-test compatibility surface only.

``requests`` and ``boto3`` are imported at module level so the integration tests
can patch ``last_connection.requests.post`` by reference; that ``requests`` is
the same module object the use case calls through.
"""

import os
import sys

# Make the hexagonal `src` package importable from this legacy CodeUri location.
_SAM_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _SAM_ROOT not in sys.path:
    sys.path.insert(0, _SAM_ROOT)

# Kept importable at module level for parity / patch compatibility.
import requests  # noqa: F401,E402
import boto3  # noqa: F401,E402

from src.core.use_cases.last_connection import (  # noqa: F401,E402
    lambda_handler,
    get_connection_status,
    is_within_last_24_hours,
    get_last_connection,
    get_creation_date,
)

__all__ = [
    "lambda_handler",
    "get_connection_status",
    "is_within_last_24_hours",
    "get_last_connection",
    "get_creation_date",
]

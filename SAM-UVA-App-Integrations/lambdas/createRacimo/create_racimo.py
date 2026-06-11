"""
create_racimo.py — LEGACY lambda-proxy shim (inbound adapter).

After the hexagonal migration the REAL logic for POST /CreateRacimo lives in
``src/core/use_cases/create_racimo.py``. This module is kept at its exact legacy
path/name with the exact ``lambda_handler(event, context)`` signature (and the
helper functions) so the existing integration tests — which do
``import create_racimo`` / ``from create_racimo import lambda_handler`` and call
the handler directly, then ``patch.object(create_racimo.requests, "post")`` —
keep passing WITHOUT modification. Behaviour (status codes, body shape,
Content-Type header, and the uncaught-exception 5xx branches) is byte-for-byte
identical.

The deployed single HTTP Lambda no longer routes through this module — it serves
POST /CreateRacimo via the FastAPI app (see src/adapters/inbound/http). This shim
is the integration-test compatibility surface only.

``requests`` and ``boto3`` are imported at module level so the integration tests
can patch ``create_racimo.requests.post`` by reference; that ``requests`` is the
same module object the use case calls through, and SigV4 signing resolves
credentials through ``boto3``.
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

from src.core.use_cases.create_racimo import (  # noqa: F401,E402
    lambda_handler,
    create_racimo,
    check_racimo_exists,
    sign_request,
    get_aws_credentials,
)

__all__ = [
    "lambda_handler",
    "create_racimo",
    "check_racimo_exists",
    "sign_request",
    "get_aws_credentials",
]

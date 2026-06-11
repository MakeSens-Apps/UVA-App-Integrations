"""
event_ingestor_uva_handler — non-HTTP Lambda entrypoint.

DynamoDB Stream (UVA table) -> MakeSens Cloud AppSync sync for the Cloud
integration. Separate Lambda (stream-triggered), not part of the HTTP API
Lambda, but built from the same ``src`` tree. Delegates to the
``uva_to_cloud`` use case.
"""

from lambda_handlers import _bootstrap  # noqa: F401  -- makes `src` importable

from src.core.use_cases.uva_to_cloud import lambda_handler as _lambda_handler


def handler(event, context):
    return _lambda_handler(event, context)

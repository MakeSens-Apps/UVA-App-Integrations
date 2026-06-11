"""
event_ingestor_measurement_handler — non-HTTP Lambda entrypoint.

DynamoDB Stream (Measurement table) -> SNS publisher for the DeviceDataAccess
integration. Separate Lambda (stream-triggered), not part of the HTTP API
Lambda, but built from the same ``src`` tree. Delegates to the
``dynamodb_to_sns`` use case.
"""

from lambda_handlers import _bootstrap  # noqa: F401  -- makes `src` importable

from src.core.use_cases.dynamodb_to_sns import lambda_handler as _lambda_handler


def handler(event, context):
    return _lambda_handler(event, context)

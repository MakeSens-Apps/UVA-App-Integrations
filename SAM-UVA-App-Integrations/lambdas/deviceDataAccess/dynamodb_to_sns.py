"""
dynamodb_to_sns.py — LEGACY shim (non-HTTP inbound adapter).

After the hexagonal migration the REAL logic for the DeviceDataAccess
integration (Measurement DynamoDB Stream -> SNS) lives in
``src/core/use_cases/dynamodb_to_sns.py``. This module is kept at its exact
legacy path/name with the exact ``lambda_handler(event, context)`` signature so
any direct imports keep working WITHOUT modification. Behaviour is byte-for-byte
identical.

The deployed Lambda for this stream now uses
``lambda_handlers.event_ingestor_measurement_handler.handler`` (CodeUri: src);
this shim is a compatibility surface only.
"""

import os
import sys

# Make the hexagonal `src` package importable from this legacy CodeUri location.
_SAM_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _SAM_ROOT not in sys.path:
    sys.path.insert(0, _SAM_ROOT)

# Kept importable at module level for parity / patch compatibility.
import boto3  # noqa: F401,E402

from src.core.use_cases.dynamodb_to_sns import (  # noqa: F401,E402
    lambda_handler,
    process_data,
    remove_data_types,
    send_message_to_topic_sns,
)

__all__ = [
    "lambda_handler",
    "process_data",
    "remove_data_types",
    "send_message_to_topic_sns",
]

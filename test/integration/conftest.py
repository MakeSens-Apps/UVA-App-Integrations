"""
Shared pytest fixtures for UVA-App-Integrations e2e tests.

Handler import notes:
- last_connection lives in lambdas/uvaConnection/ — imported by inserting that dir at sys.path[0]
- create_racimo lives in lambdas/createRacimo/  — imported by inserting that dir at sys.path[0]
Both dirs are inserted lazily (inside each test file) to avoid module-name collisions at
collection time.  This conftest only owns environment-variable fixtures that both test
files share.
"""

import os
import sys
import json

import pytest

# ---------------------------------------------------------------------------
# AWS fake credentials — must be set before any boto3/botocore import so that
# SigV4Auth can resolve credentials without hitting the real metadata service.
# ---------------------------------------------------------------------------
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")


# ---------------------------------------------------------------------------
# Shared AppSync URL constant
# ---------------------------------------------------------------------------
APPSYNC_URL = (
    "https://swmmbj4xmfa5pelhgbljkxonuu.appsync-api.us-east-1.amazonaws.com/graphql"
)
API_KEY = "da2-test-key"


# ---------------------------------------------------------------------------
# Fixtures: environment variables for last_connection handler
# ---------------------------------------------------------------------------
@pytest.fixture()
def last_connection_env(monkeypatch):
    """Set env vars required by the last_connection handler."""
    monkeypatch.setenv("AppSyncURL", APPSYNC_URL)
    monkeypatch.setenv("ApiKey", API_KEY)
    yield
    # monkeypatch restores originals automatically


@pytest.fixture()
def last_connection_env_missing(monkeypatch):
    """Remove the env vars so the handler raises KeyError on access."""
    monkeypatch.delenv("AppSyncURL", raising=False)
    monkeypatch.delenv("ApiKey", raising=False)
    yield


# ---------------------------------------------------------------------------
# Fixtures: environment variables for create_racimo handler
# ---------------------------------------------------------------------------
@pytest.fixture()
def create_racimo_env(monkeypatch):
    """Set env vars required by the create_racimo handler."""
    monkeypatch.setenv("AppSyncURL", APPSYNC_URL)
    # Also keep fake AWS creds in scope for SigV4
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    yield


# ---------------------------------------------------------------------------
# Minimal Lambda context stub
# ---------------------------------------------------------------------------
class FakeLambdaContext:
    function_name = "test-function"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    memory_limit_in_mb = 128
    aws_request_id = "test-request-id"
    log_group_name = "/aws/lambda/test-function"
    log_stream_name = "2026/06/10/[$LATEST]test"
    remaining_time_in_millis = lambda self: 30000


@pytest.fixture()
def lambda_context():
    return FakeLambdaContext()

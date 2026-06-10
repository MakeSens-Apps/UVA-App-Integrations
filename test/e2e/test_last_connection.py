"""
E2E tests for GET /{id_uva}/connection  (last_connection.lambda_handler).

The handler reaches AppSync over plain HTTP (requests.post) — no boto3 service
clients are called for its core logic.  All network calls are intercepted with
the 'responses' library (or unittest.mock) so no real AWS connectivity is needed.

Import strategy: insert the source lambda directory at sys.path[0] right here so
the module is importable as `last_connection`.  We do this at module-load time
inside a try/except so that if the path was already added by a previous test run
in the same session we simply re-use the cached module.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject the handler's source directory BEFORE importing the module so Python
# finds the right file and not a stale .aws-sam/build copy.
# ---------------------------------------------------------------------------
_HANDLER_DIR = (
    "/Users/jose.salamanca/Documents/code/makesens/MakeSens-Apps/"
    "UVA-App-Integrations/SAM-UVA-App-Integrations/lambdas/uvaConnection"
)
if _HANDLER_DIR not in sys.path:
    sys.path.insert(0, _HANDLER_DIR)

import last_connection as _lc_module  # noqa: E402 — must come after sys.path manipulation
from last_connection import lambda_handler  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
APPSYNC_URL = (
    "https://swmmbj4xmfa5pelhgbljkxonuu.appsync-api.us-east-1.amazonaws.com/graphql"
)


def _now_iso_z() -> str:
    """Return the current UTC time formatted as ISO-8601 with a Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _old_iso_z(hours: int = 48) -> str:
    """Return an ISO-8601 timestamp `hours` hours in the past."""
    past = datetime.now(timezone.utc) - timedelta(hours=hours)
    return past.strftime("%Y-%m-%dT%H:%M:%SZ")


def _mock_response(json_body: dict, status_code: int = 200):
    """Build a minimal requests.Response mock."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.text = json.dumps(json_body)
    return mock


def _apigw_event(id_uva: str, query_params=None) -> dict:
    """Build a minimal API Gateway proxy event."""
    return {
        "pathParameters": {"id_uva": id_uva},
        "queryStringParameters": query_params,
        "httpMethod": "GET",
        "headers": {},
        "body": None,
    }


# ---------------------------------------------------------------------------
# GREEN TESTS
# ---------------------------------------------------------------------------


class TestSingleUvaRecentMeasurement:
    """Single device — measurement within the last 24 h → connection True."""

    def test_single_uva_recent_measurement_returns_200_when_within_24h(
        self, last_connection_env, lambda_context
    ):
        recent_ts = _now_iso_z()
        measurement_resp = _mock_response(
            {
                "data": {
                    "measurementsByUvaIDAndTs": {
                        "items": [{"ts": recent_ts, "createdAt": recent_ts}]
                    }
                }
            }
        )

        with patch.object(_lc_module.requests, "post", return_value=measurement_resp):
            response = lambda_handler(_apigw_event("uva-001"), lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "uva-001" in body
        device = body["uva-001"]
        assert device["connection"] is True
        assert "ts" in device
        assert isinstance(device["ts"], int)

    def test_single_uva_recent_measurement_connection_flag_is_boolean(
        self, last_connection_env, lambda_context
    ):
        recent_ts = _now_iso_z()
        measurement_resp = _mock_response(
            {
                "data": {
                    "measurementsByUvaIDAndTs": {
                        "items": [{"ts": recent_ts, "createdAt": recent_ts}]
                    }
                }
            }
        )

        with patch.object(_lc_module.requests, "post", return_value=measurement_resp):
            response = lambda_handler(_apigw_event("uva-001"), lambda_context)

        body = json.loads(response["body"])
        assert isinstance(body["uva-001"]["connection"], bool)


class TestSingleUvaOldMeasurement:
    """Single device — measurement older than 24 h → connection False."""

    def test_single_uva_old_measurement_returns_200_when_older_than_24h(
        self, last_connection_env, lambda_context
    ):
        old_ts = _old_iso_z(hours=48)
        measurement_resp = _mock_response(
            {
                "data": {
                    "measurementsByUvaIDAndTs": {
                        "items": [{"ts": old_ts, "createdAt": old_ts}]
                    }
                }
            }
        )

        with patch.object(_lc_module.requests, "post", return_value=measurement_resp):
            response = lambda_handler(_apigw_event("uva-002"), lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "uva-002" in body
        assert body["uva-002"]["connection"] is False
        assert "ts" in body["uva-002"]

    def test_single_uva_old_measurement_ts_is_unix_milliseconds(
        self, last_connection_env, lambda_context
    ):
        old_ts = _old_iso_z(hours=72)
        measurement_resp = _mock_response(
            {
                "data": {
                    "measurementsByUvaIDAndTs": {
                        "items": [{"ts": old_ts, "createdAt": old_ts}]
                    }
                }
            }
        )

        with patch.object(_lc_module.requests, "post", return_value=measurement_resp):
            response = lambda_handler(_apigw_event("uva-002"), lambda_context)

        body = json.loads(response["body"])
        ts_value = body["uva-002"]["ts"]
        # Timestamps in ms should be a large integer (> year 2000 in ms)
        assert ts_value > 946_684_800_000


class TestSingleUvaNoMeasurementFallback:
    """No measurement items returned — handler falls back to getUVA createdAt."""

    def test_single_uva_no_measurement_falls_back_to_creation_date_returns_200(
        self, last_connection_env, lambda_context
    ):
        empty_measurement_resp = _mock_response(
            {"data": {"measurementsByUvaIDAndTs": {"items": []}}}
        )
        creation_resp = _mock_response(
            {"data": {"getUVA": {"createdAt": "2026-06-01T00:00:00Z"}}}
        )

        call_counter = {"n": 0}

        def side_effect(*args, **kwargs):
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return empty_measurement_resp
            return creation_resp

        with patch.object(_lc_module.requests, "post", side_effect=side_effect):
            response = lambda_handler(_apigw_event("uva-003"), lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "uva-003" in body

    def test_single_uva_no_measurement_fallback_makes_two_appsync_calls(
        self, last_connection_env, lambda_context
    ):
        empty_measurement_resp = _mock_response(
            {"data": {"measurementsByUvaIDAndTs": {"items": []}}}
        )
        creation_resp = _mock_response(
            {"data": {"getUVA": {"createdAt": "2026-06-01T00:00:00Z"}}}
        )

        responses_list = [empty_measurement_resp, creation_resp]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_list[idx]

        with patch.object(_lc_module.requests, "post", side_effect=side_effect) as mock_post:
            lambda_handler(_apigw_event("uva-003"), lambda_context)

        assert mock_post.call_count == 2

    def test_single_uva_no_measurement_no_fallback_returns_none_for_device(
        self, last_connection_env, lambda_context
    ):
        """When both queries return empty/None, device entry is None."""
        empty_measurement_resp = _mock_response(
            {"data": {"measurementsByUvaIDAndTs": {"items": []}}}
        )
        empty_creation_resp = _mock_response(
            {"data": {"getUVA": {"createdAt": None}}}
        )

        responses_list = [empty_measurement_resp, empty_creation_resp]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_list[idx]

        with patch.object(_lc_module.requests, "post", side_effect=side_effect):
            response = lambda_handler(_apigw_event("uva-003"), lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        # get_connection_status returns None when lastConnection is falsy
        assert body["uva-003"] is None


class TestAllModeMultipleIds:
    """id_uva='all' with comma-separated 'id' query param."""

    def test_all_mode_multiple_ids_returns_200_with_each_key(
        self, last_connection_env, lambda_context
    ):
        recent_ts = _now_iso_z()
        mocked_response = _mock_response(
            {
                "data": {
                    "measurementsByUvaIDAndTs": {
                        "items": [{"ts": recent_ts, "createdAt": recent_ts}]
                    }
                }
            }
        )

        event = _apigw_event("all", query_params={"id": "uvaA,uvaB"})

        with patch.object(_lc_module.requests, "post", return_value=mocked_response):
            response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "uvaA" in body
        assert "uvaB" in body

    def test_all_mode_each_device_has_connection_and_ts_fields(
        self, last_connection_env, lambda_context
    ):
        recent_ts = _now_iso_z()
        mocked_response = _mock_response(
            {
                "data": {
                    "measurementsByUvaIDAndTs": {
                        "items": [{"ts": recent_ts, "createdAt": recent_ts}]
                    }
                }
            }
        )

        event = _apigw_event("all", query_params={"id": "uvaA,uvaB"})

        with patch.object(_lc_module.requests, "post", return_value=mocked_response):
            response = lambda_handler(event, lambda_context)

        body = json.loads(response["body"])
        for device_id in ["uvaA", "uvaB"]:
            device = body[device_id]
            assert "connection" in device
            assert "ts" in device

    def test_all_mode_single_id_in_list_returns_one_key(
        self, last_connection_env, lambda_context
    ):
        recent_ts = _now_iso_z()
        mocked_response = _mock_response(
            {
                "data": {
                    "measurementsByUvaIDAndTs": {
                        "items": [{"ts": recent_ts, "createdAt": recent_ts}]
                    }
                }
            }
        )

        event = _apigw_event("all", query_params={"id": "uvaOnly"})

        with patch.object(_lc_module.requests, "post", return_value=mocked_response):
            response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "uvaOnly" in body
        assert len(body) == 1


# ---------------------------------------------------------------------------
# RED TESTS
# ---------------------------------------------------------------------------


class TestMissingPathParametersIdUva:
    """Missing pathParameters / id_uva → KeyError (no try/except in handler)."""

    def test_missing_path_parameters_id_uva_raises_key_error(
        self, last_connection_env, lambda_context
    ):
        event_without_path_params = {
            "queryStringParameters": None,
            "httpMethod": "GET",
            "headers": {},
            "body": None,
        }

        with pytest.raises(KeyError):
            lambda_handler(event_without_path_params, lambda_context)

    def test_missing_id_uva_key_within_path_parameters_raises_key_error(
        self, last_connection_env, lambda_context
    ):
        event_with_empty_path_params = {
            "pathParameters": {},
            "queryStringParameters": None,
            "httpMethod": "GET",
            "headers": {},
            "body": None,
        }

        with pytest.raises(KeyError):
            lambda_handler(event_with_empty_path_params, lambda_context)


class TestAllModeWithoutIdQueryParam:
    """id_uva='all' but no 'id' query param → AttributeError (None.split)."""

    def test_all_mode_without_id_query_param_raises_attribute_error(
        self, last_connection_env, lambda_context
    ):
        event = {
            "pathParameters": {"id_uva": "all"},
            "queryStringParameters": {},
            "httpMethod": "GET",
            "headers": {},
            "body": None,
        }

        with pytest.raises(AttributeError):
            lambda_handler(event, lambda_context)

    def test_all_mode_null_query_string_parameters_raises_attribute_error(
        self, last_connection_env, lambda_context
    ):
        """queryStringParameters=None collapses to {}, 'id' missing -> AttributeError."""
        event = {
            "pathParameters": {"id_uva": "all"},
            "queryStringParameters": None,  # handled by `or {}` -> empty dict
            "httpMethod": "GET",
            "headers": {},
            "body": None,
        }

        with pytest.raises(AttributeError):
            lambda_handler(event, lambda_context)


class TestMissingEnvVars:
    """AppSyncURL / ApiKey not set → KeyError on os.environ access."""

    def test_missing_env_vars_raises_key_error(
        self, last_connection_env_missing, lambda_context
    ):
        event = _apigw_event("uva-001")

        with pytest.raises(KeyError):
            lambda_handler(event, lambda_context)

    def test_missing_appsync_url_raises_key_error(
        self, monkeypatch, lambda_context
    ):
        monkeypatch.delenv("AppSyncURL", raising=False)
        monkeypatch.setenv("ApiKey", "some-key")

        event = _apigw_event("uva-001")

        with pytest.raises(KeyError):
            lambda_handler(event, lambda_context)

    def test_missing_api_key_raises_key_error(
        self, monkeypatch, lambda_context
    ):
        monkeypatch.setenv("AppSyncURL", "https://example.appsync-api.amazonaws.com/graphql")
        monkeypatch.delenv("ApiKey", raising=False)

        event = _apigw_event("uva-001")

        with pytest.raises(KeyError):
            lambda_handler(event, lambda_context)

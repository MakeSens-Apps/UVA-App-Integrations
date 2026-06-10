"""
E2E tests for POST /CreateRacimo  (create_racimo.lambda_handler).

The handler:
1. Parses JSON body for 'name' and 'linkageCode'.
2. Calls check_racimo_exists (SigV4-signed POST to AppSync listRACIMOS).
3. If not found, calls create_racimo (SigV4-signed POST to AppSync createRACIMO).

All network calls are intercepted via unittest.mock.patch so no real AWS or
AppSync connectivity is needed.  SigV4 signing is exercised with the fake
AWS credentials injected by the `create_racimo_env` fixture (which sets
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION env vars so
botocore resolves credentials from the environment without hitting the
EC2 metadata service).

Import strategy: insert the source lambda directory at sys.path[0] here at
module load time (before the import) to avoid picking up a stale
.aws-sam/build copy.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject the handler's source directory BEFORE importing the module.
# ---------------------------------------------------------------------------
_HANDLER_DIR = (
    "/Users/jose.salamanca/Documents/code/makesens/MakeSens-Apps/"
    "UVA-App-Integrations/SAM-UVA-App-Integrations/lambdas/createRacimo"
)
if _HANDLER_DIR not in sys.path:
    sys.path.insert(0, _HANDLER_DIR)

import create_racimo as _cr_module  # noqa: E402
from create_racimo import lambda_handler  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
APPSYNC_URL = (
    "https://swmmbj4xmfa5pelhgbljkxonuu.appsync-api.us-east-1.amazonaws.com/graphql"
)


def _mock_response(json_body: dict, status_code: int = 200):
    """Build a minimal requests.Response mock."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.text = json.dumps(json_body)
    return mock


def _apigw_event(body_dict: dict | None, raw_body: str | None = None) -> dict:
    """Build a minimal API Gateway proxy event for POST /CreateRacimo."""
    if raw_body is not None:
        body_str = raw_body
    elif body_dict is not None:
        body_str = json.dumps(body_dict)
    else:
        body_str = None  # triggers TypeError in handler

    return {
        "httpMethod": "POST",
        "path": "/CreateRacimo",
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": None,
        "body": body_str,
    }


def _check_not_exists_response():
    return _mock_response({"data": {"listRACIMOS": {"items": []}}})


def _check_exists_response(name: str = "Racimo Test", linkage_code: str = "LC-200"):
    return _mock_response(
        {
            "data": {
                "listRACIMOS": {
                    "items": [{"Name": name, "LinkageCode": linkage_code}]
                }
            }
        }
    )


def _create_success_response(racimo_id: str = "racimo-123"):
    return _mock_response(
        {"data": {"createRACIMO": {"id": racimo_id}}}
    )


# ---------------------------------------------------------------------------
# GREEN TESTS
# ---------------------------------------------------------------------------


class TestCreateNewRacimo:
    """LinkageCode does not exist → mutation creates it → return racimoId."""

    def test_create_new_racimo_returns_200_with_racimo_id(
        self, create_racimo_env, lambda_context
    ):
        responses_seq = [_check_not_exists_response(), _create_success_response()]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-100"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True
        assert "racimoId" in body
        assert body["racimoId"] == "racimo-123"

    def test_create_new_racimo_response_has_message_key(
        self, create_racimo_env, lambda_context
    ):
        responses_seq = [_check_not_exists_response(), _create_success_response()]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-100"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            response = lambda_handler(event, lambda_context)

        body = json.loads(response["body"])
        assert "message" in body
        assert isinstance(body["message"], str)

    def test_create_new_racimo_success_flag_is_true(
        self, create_racimo_env, lambda_context
    ):
        responses_seq = [_check_not_exists_response(), _create_success_response()]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "New Racimo", "linkageCode": "LC-NEW"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            response = lambda_handler(event, lambda_context)

        body = json.loads(response["body"])
        assert body["success"] is True

    def test_create_new_racimo_makes_two_appsync_calls(
        self, create_racimo_env, lambda_context
    ):
        """Two POST calls: one for check, one for create."""
        responses_seq = [_check_not_exists_response(), _create_success_response()]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-100"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect) as mock_post:
            lambda_handler(event, lambda_context)

        assert mock_post.call_count == 2


class TestExistingRacimo:
    """RACIMO with given LinkageCode already exists → return existing data."""

    def test_existing_racimo_returns_200_with_result_key(
        self, create_racimo_env, lambda_context
    ):
        exists_resp = _check_exists_response(name="Racimo Test", linkage_code="LC-200")
        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-200"})

        with patch.object(_cr_module.requests, "post", return_value=exists_resp):
            response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "result" in body

    def test_existing_racimo_returns_success_true(
        self, create_racimo_env, lambda_context
    ):
        exists_resp = _check_exists_response(name="Racimo Test", linkage_code="LC-200")
        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-200"})

        with patch.object(_cr_module.requests, "post", return_value=exists_resp):
            response = lambda_handler(event, lambda_context)

        body = json.loads(response["body"])
        assert body["success"] is True

    def test_existing_racimo_returns_message_key(
        self, create_racimo_env, lambda_context
    ):
        exists_resp = _check_exists_response(name="Racimo Test", linkage_code="LC-200")
        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-200"})

        with patch.object(_cr_module.requests, "post", return_value=exists_resp):
            response = lambda_handler(event, lambda_context)

        body = json.loads(response["body"])
        assert "message" in body

    def test_existing_racimo_result_contains_name_and_linkage_code(
        self, create_racimo_env, lambda_context
    ):
        exists_resp = _check_exists_response(name="Racimo Test", linkage_code="LC-200")
        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-200"})

        with patch.object(_cr_module.requests, "post", return_value=exists_resp):
            response = lambda_handler(event, lambda_context)

        body = json.loads(response["body"])
        result = body["result"]
        assert result["Name"] == "Racimo Test"
        assert result["LinkageCode"] == "LC-200"

    def test_existing_racimo_does_not_call_create_mutation(
        self, create_racimo_env, lambda_context
    ):
        """When racimo exists, only one POST should be made (the check query)."""
        exists_resp = _check_exists_response(name="Racimo Test", linkage_code="LC-200")
        event = _apigw_event({"name": "Racimo Test", "linkageCode": "LC-200"})

        with patch.object(_cr_module.requests, "post", return_value=exists_resp) as mock_post:
            lambda_handler(event, lambda_context)

        assert mock_post.call_count == 1


class TestCreateRacimoResponseHeaders:
    """Verify Content-Type header is present in success responses."""

    def test_create_racimo_response_has_content_type_application_json(
        self, create_racimo_env, lambda_context
    ):
        responses_seq = [_check_not_exists_response(), _create_success_response("racimo-300")]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "R", "linkageCode": "LC-300"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            response = lambda_handler(event, lambda_context)

        assert response["statusCode"] == 200
        headers = response.get("headers", {})
        assert headers.get("Content-Type") == "application/json"

    def test_existing_racimo_response_has_content_type_application_json(
        self, create_racimo_env, lambda_context
    ):
        exists_resp = _check_exists_response(name="R", linkage_code="LC-300")
        event = _apigw_event({"name": "R", "linkageCode": "LC-300"})

        with patch.object(_cr_module.requests, "post", return_value=exists_resp):
            response = lambda_handler(event, lambda_context)

        headers = response.get("headers", {})
        assert headers.get("Content-Type") == "application/json"

    def test_create_racimo_success_body_is_valid_json_string(
        self, create_racimo_env, lambda_context
    ):
        responses_seq = [_check_not_exists_response(), _create_success_response("racimo-300")]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "R", "linkageCode": "LC-300"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            response = lambda_handler(event, lambda_context)

        # Must be parseable as JSON
        parsed = json.loads(response["body"])
        assert isinstance(parsed, dict)
        assert "success" in parsed
        assert "racimoId" in parsed


# ---------------------------------------------------------------------------
# RED TESTS
# ---------------------------------------------------------------------------


class TestMissingBody:
    """event has no body (None) → json.loads(None) raises TypeError."""

    def test_missing_body_raises_type_error(
        self, create_racimo_env, lambda_context
    ):
        event = {}  # event.get('body') is None

        with pytest.raises(TypeError):
            lambda_handler(event, lambda_context)

    def test_explicit_none_body_raises_type_error(
        self, create_racimo_env, lambda_context
    ):
        event = {"body": None}

        with pytest.raises(TypeError):
            lambda_handler(event, lambda_context)


class TestInvalidJsonBody:
    """body is not valid JSON → json.JSONDecodeError."""

    def test_invalid_json_body_raises_json_decode_error(
        self, create_racimo_env, lambda_context
    ):
        event = _apigw_event(None, raw_body="not-json")

        with pytest.raises(json.JSONDecodeError):
            lambda_handler(event, lambda_context)

    def test_empty_string_body_raises_json_decode_error(
        self, create_racimo_env, lambda_context
    ):
        event = _apigw_event(None, raw_body="")

        with pytest.raises((json.JSONDecodeError, ValueError)):
            lambda_handler(event, lambda_context)

    def test_partial_json_body_raises_json_decode_error(
        self, create_racimo_env, lambda_context
    ):
        event = _apigw_event(None, raw_body='{"name": "R"')  # missing closing brace

        with pytest.raises(json.JSONDecodeError):
            lambda_handler(event, lambda_context)


class TestCreateRacimoAppSyncNon200:
    """AppSync createRACIMO returns non-200 → Exception propagated."""

    def test_create_racimo_appsync_500_raises_exception(
        self, create_racimo_env, lambda_context
    ):
        check_resp = _check_not_exists_response()
        error_resp = _mock_response({"message": "Internal Server Error"}, status_code=500)

        responses_seq = [check_resp, error_resp]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "R", "linkageCode": "LC-ERR"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            with pytest.raises(Exception) as exc_info:
                lambda_handler(event, lambda_context)

        assert "500" in str(exc_info.value)

    def test_create_racimo_appsync_401_raises_exception(
        self, create_racimo_env, lambda_context
    ):
        check_resp = _check_not_exists_response()
        auth_error_resp = _mock_response({"message": "Unauthorized"}, status_code=401)

        responses_seq = [check_resp, auth_error_resp]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "R", "linkageCode": "LC-UNAUTH"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            with pytest.raises(Exception) as exc_info:
                lambda_handler(event, lambda_context)

        assert "401" in str(exc_info.value)

    def test_create_racimo_check_appsync_failure_raises_exception(
        self, create_racimo_env, lambda_context
    ):
        """check_racimo_exists itself also raises when AppSync returns non-200."""
        error_resp = _mock_response({"message": "Service Unavailable"}, status_code=503)
        event = _apigw_event({"name": "R", "linkageCode": "LC-DOWN"})

        with patch.object(_cr_module.requests, "post", return_value=error_resp):
            with pytest.raises(Exception):
                lambda_handler(event, lambda_context)

    def test_create_racimo_exception_message_contains_error_details(
        self, create_racimo_env, lambda_context
    ):
        """The raised Exception message should include status code and response body."""
        check_resp = _check_not_exists_response()
        error_body = {"error": "something went wrong"}
        error_resp = _mock_response(error_body, status_code=500)

        responses_seq = [check_resp, error_resp]
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            return responses_seq[idx]

        event = _apigw_event({"name": "R", "linkageCode": "LC-ERR2"})

        with patch.object(_cr_module.requests, "post", side_effect=side_effect):
            with pytest.raises(Exception) as exc_info:
                lambda_handler(event, lambda_context)

        error_msg = str(exc_info.value)
        # The handler formats the message as: "Error al procesar la solicitud: {status} - {text}"
        assert "Error al procesar la solicitud" in error_msg


class TestMissingEnvVarsCreateRacimo:
    """AppSyncURL env var not set → KeyError on os.environ access."""

    def test_missing_appsync_url_raises_key_error(
        self, monkeypatch, lambda_context
    ):
        monkeypatch.delenv("AppSyncURL", raising=False)

        event = _apigw_event({"name": "R", "linkageCode": "LC-100"})

        with pytest.raises(KeyError):
            lambda_handler(event, lambda_context)

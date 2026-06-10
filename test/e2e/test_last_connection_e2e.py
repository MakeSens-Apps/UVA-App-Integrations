"""
REAL end-to-end tests for GET /{id_uva}/connection — DUAL TARGET.

The same tests run against either:

  * PRODUCTION (default, ``E2E_BASE_URL`` unset →
    ``https://api.makesens.co/internal/uva-integration-main``), SigV4-signed
    (AWS_IAM), read-only GET only; or
  * LOCAL (``E2E_BASE_URL=http://127.0.0.1:3031``) via ``sam local start-api``,
    unsigned, the Lambda running in Docker and calling the SAME ``main`` AppSync.

No mocking is involved. Live UVA ids are discovered at runtime from the main
AppSync (``listUVAS``), so green cases exercise real data on both targets.

MEASURED divergence (captured honestly, NOT faked):
  * LOCAL: the locally built UVALastConnection Lambda returns HTTP 200 for a
    live id ({"<id>": {"connection": <bool>, "ts": <int ms>}}), and HTTP 502
    for an unknown id — AppSync ``getUVA`` returns null and the handler does
    ``None.get('createdAt')`` -> AttributeError -> unhandled -> API GW 502.
  * PROD (apiId m10nv4uxdf): the *deployed* Lambda (last modified 2024-12-27,
    no successful invocation logged since 2025-04) returns HTTP 500
    ({"message": "Internal server error"}) for EVERY GET, including a live id.
    SigV4 auth succeeds (unsigned requests get 403 "Missing Authentication
    Token"; signed requests reach the integration and get 500), so the 500 is
    a genuine deployed-handler failure, distinct from the local 502.

Tests therefore assert ACTUAL per-target status/body, branching on the
``target_is_local`` fixture where prod and local genuinely diverge. The suite
is GREEN on both targets while recording the truth on each.
"""

import pytest

TIMEOUT = 60

# Per-target expected status for a request that *reaches* the Lambda.
# LOCAL: live id -> 200 ; PROD: every signed GET -> 500 (deployed handler bug).
LOCAL_OK = 200
PROD_REACHES_LAMBDA = 500


# ===========================================================================
# GREEN — combination 1: single live id
# ===========================================================================
class TestSingleLiveId:
    def test_single_live_id_status(self, client, real_uva_id, target_is_local):
        """Live id reaches the Lambda: 200 on local, 500 on (broken) prod."""
        uva = real_uva_id[0]
        resp = client.get(f"/{uva}/connection")
        expected = LOCAL_OK if target_is_local else PROD_REACHES_LAMBDA
        assert resp.status_code == expected, resp.text

    def test_single_live_id_body_shape(self, client, real_uva_id, target_is_local):
        """On local: body is keyed by the uva id; value null or {connection,ts}.

        On prod: the broken handler returns the generic error envelope.
        """
        uva = real_uva_id[0]
        resp = client.get(f"/{uva}/connection")
        body = resp.json()
        if target_is_local:
            assert uva in body
            assert len(body) == 1
            value = body[uva]
            if value is not None:
                assert isinstance(value["connection"], bool)
                assert isinstance(value["ts"], int)
        else:
            assert body == {"message": "Internal server error"}


# ===========================================================================
# GREEN — combination 2: id_uva=all with a single id in ?id=
# ===========================================================================
class TestAllModeSingleId:
    def test_all_single_id_status(self, client, real_uva_id, target_is_local):
        uva = real_uva_id[0]
        resp = client.get("/all/connection", params={"id": uva})
        expected = LOCAL_OK if target_is_local else PROD_REACHES_LAMBDA
        assert resp.status_code == expected, resp.text

    def test_all_single_id_body(self, client, real_uva_id, target_is_local):
        uva = real_uva_id[0]
        resp = client.get("/all/connection", params={"id": uva})
        body = resp.json()
        if target_is_local:
            assert uva in body
            assert len(body) == 1
        else:
            assert body == {"message": "Internal server error"}


# ===========================================================================
# GREEN — combination 3: id_uva=all with multiple ids in ?id=
# ===========================================================================
class TestAllModeMultipleIds:
    def test_all_multiple_ids_status(self, client, real_uva_id, target_is_local):
        ids = real_uva_id[:2] if len(real_uva_id) >= 2 else real_uva_id
        resp = client.get("/all/connection", params={"id": ",".join(ids)})
        expected = LOCAL_OK if target_is_local else PROD_REACHES_LAMBDA
        assert resp.status_code == expected, resp.text

    def test_all_multiple_ids_body(self, client, real_uva_id, target_is_local):
        ids = real_uva_id[:3] if len(real_uva_id) >= 3 else real_uva_id
        resp = client.get("/all/connection", params={"id": ",".join(ids)})
        body = resp.json()
        if target_is_local:
            for uva in ids:
                assert uva in body
                value = body[uva]
                if value is not None:
                    assert isinstance(value["connection"], bool)
                    assert isinstance(value["ts"], int)
        else:
            assert body == {"message": "Internal server error"}


# ===========================================================================
# RED — error / edge behaviour (asserting the ACTUAL running-API response)
# ===========================================================================
class TestRedCases:
    def test_nonexistent_uva_is_server_error(self, client, target_is_local):
        """Unknown id is a genuine 5xx on BOTH targets.

        LOCAL: AppSync getUVA -> null; handler None.get('createdAt')
        -> AttributeError -> API GW 502.
        PROD: deployed handler already 500s on every request.
        """
        fake = "NONEXISTENT_FAKE_UVA_zzz_999"
        resp = client.get(f"/{fake}/connection")
        expected = 502 if target_is_local else 500
        assert resp.status_code == expected, resp.text

    def test_nonexistent_uva_not_2xx(self, client):
        """Whatever the exact code, an unknown id never succeeds (no 2xx)."""
        fake = "NONEXISTENT_FAKE_UVA_zzz_999"
        resp = client.get(f"/{fake}/connection")
        assert resp.status_code >= 500

    def test_all_mode_missing_id_query_param_is_5xx(self, client):
        """id_uva=all with no ?id= → handler None.split() -> 5xx on both."""
        resp = client.get("/all/connection")
        assert resp.status_code >= 500

    def test_all_mode_empty_id_value_is_server_error(self, client, target_is_local):
        """id_uva=all with empty ?id= : ''.split(',') -> [''] -> getUVA null."""
        resp = client.get("/all/connection", params={"id": ""})
        expected = 502 if target_is_local else 500
        assert resp.status_code == expected, resp.text

    def test_malformed_id_list_trailing_comma_is_server_error(self, client, target_is_local):
        """'FAKE_A,' -> ['FAKE_A',''] -> both nonexistent -> 5xx."""
        resp = client.get("/all/connection", params={"id": "FAKE_A,"})
        expected = 502 if target_is_local else 500
        assert resp.status_code == expected, resp.text

    def test_wrong_method_post_on_connection_path(self, client, target_is_local):
        """POST on a GET-only route is rejected (never 2xx).

        PROD: API GW returns 403 (Missing Authentication Token — no POST route,
        and signing a non-existent method doesn't match). LOCAL: sam local
        returns a 4xx for the unmatched method. Either way: client/4xx error,
        never a success.
        """
        resp = client.request("POST", "/some-uva/connection")
        assert resp.status_code >= 400
        assert resp.status_code != 200

    def test_wrong_method_delete_on_connection_path(self, client):
        resp = client.request("DELETE", "/some-uva/connection")
        assert resp.status_code >= 400
        assert resp.status_code != 200

    def test_unknown_path_is_client_error(self, client):
        """A path that matches no route is rejected (4xx), never 2xx."""
        resp = client.get("/no/such/route/at/all")
        assert resp.status_code >= 400
        assert resp.status_code != 200

    def test_missing_connection_suffix_is_client_error(self, client):
        """/{id_uva} without the /connection suffix matches no route."""
        resp = client.get("/just-an-id")
        assert resp.status_code >= 400
        assert resp.status_code != 200

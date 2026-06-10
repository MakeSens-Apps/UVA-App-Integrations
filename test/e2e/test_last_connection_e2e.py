"""
REAL end-to-end tests for GET /{id_uva}/connection.

These tests drive the *deployed* UVALastConnection Lambda through a real
``sam local start-api`` gateway (Lambda running in Docker) and let it make REAL
HTTP calls to the REAL UVA AppSync GraphQL API (read-only, API-key auth). No
mocking is involved anywhere in this file.

Behaviour reference (confirmed against the live develop AppSync):
  * A live UVA id with no recent measurement falls back to getUVA.createdAt,
    yielding {"connection": <bool>, "ts": <int ms>}.
  * A NONEXISTENT UVA id triggers a REAL 502: AppSync returns
    ``{"data": {"getUVA": null}}``; the handler's get_creation_date does
    ``data.get('data', {}).get('getUVA', {}).get('createdAt')`` which, because
    the ``getUVA`` key is present with value ``None``, evaluates to
    ``None.get('createdAt')`` -> AttributeError -> unhandled -> API Gateway 502.
    This is a genuine handler BUG (the ``, {}`` default is never used when the
    key exists with a null value); the e2e red tests below assert the ACTUAL
    502 rather than the (intended-but-wrong) graceful null.

The ``api_base_url`` and ``real_uva_id`` fixtures live in conftest.py and skip
the whole module gracefully when Docker / sam / AppSync creds are unavailable.
"""

import requests

CONN_PATH = "/{id}/connection"
TIMEOUT = 60


def _get(base, path, **kwargs):
    return requests.get(f"{base}{path}", timeout=TIMEOUT, **kwargs)


# ===========================================================================
# GREEN — combination 1: single live id
# ===========================================================================
class TestSingleLiveId:
    def test_single_live_id_returns_200(self, api_base_url, real_uva_id):
        uva = real_uva_id[0]
        resp = _get(api_base_url, f"/{uva}/connection")
        assert resp.status_code == 200

    def test_single_live_id_body_keyed_by_uva(self, api_base_url, real_uva_id):
        uva = real_uva_id[0]
        resp = _get(api_base_url, f"/{uva}/connection")
        body = resp.json()
        assert uva in body
        assert len(body) == 1

    def test_single_live_id_value_shape(self, api_base_url, real_uva_id):
        """Per-id value is either null OR a dict with connection(bool)+ts(int)."""
        uva = real_uva_id[0]
        resp = _get(api_base_url, f"/{uva}/connection")
        value = resp.json()[uva]
        if value is not None:
            assert isinstance(value["connection"], bool)
            assert isinstance(value["ts"], int)


# ===========================================================================
# GREEN — combination 2: id_uva=all with a single id in ?id=
# ===========================================================================
class TestAllModeSingleId:
    def test_all_single_id_returns_200(self, api_base_url, real_uva_id):
        uva = real_uva_id[0]
        resp = _get(api_base_url, f"/all/connection", params={"id": uva})
        assert resp.status_code == 200

    def test_all_single_id_body_has_one_key(self, api_base_url, real_uva_id):
        uva = real_uva_id[0]
        resp = _get(api_base_url, f"/all/connection", params={"id": uva})
        body = resp.json()
        assert uva in body
        assert len(body) == 1


# ===========================================================================
# GREEN — combination 3: id_uva=all with multiple ids in ?id=
# ===========================================================================
class TestAllModeMultipleIds:
    def test_all_multiple_ids_returns_200(self, api_base_url, real_uva_id):
        ids = real_uva_id[:2] if len(real_uva_id) >= 2 else real_uva_id
        resp = _get(api_base_url, f"/all/connection", params={"id": ",".join(ids)})
        assert resp.status_code == 200

    def test_all_multiple_ids_body_has_every_key(self, api_base_url, real_uva_id):
        ids = real_uva_id[:2] if len(real_uva_id) >= 2 else real_uva_id
        resp = _get(api_base_url, f"/all/connection", params={"id": ",".join(ids)})
        body = resp.json()
        for uva in ids:
            assert uva in body

    def test_all_multiple_ids_each_value_shape(self, api_base_url, real_uva_id):
        ids = real_uva_id[:3] if len(real_uva_id) >= 3 else real_uva_id
        resp = _get(api_base_url, f"/all/connection", params={"id": ",".join(ids)})
        body = resp.json()
        for uva in ids:
            value = body[uva]
            if value is not None:
                assert isinstance(value["connection"], bool)
                assert isinstance(value["ts"], int)


# ===========================================================================
# RED — error / edge behaviour (asserting the ACTUAL running-API response)
# ===========================================================================
class TestRedCases:
    def test_nonexistent_uva_returns_502_handler_bug(self, api_base_url):
        """Nonexistent id: REAL behaviour is HTTP 502 (handler bug).

        AppSync getUVA returns null; get_creation_date does None.get('createdAt')
        -> AttributeError -> unhandled exception -> API Gateway 502.
        Layer hit: Lambda handler logic (crash) + real AppSync (getUVA=null).
        """
        fake = "NONEXISTENT_FAKE_UVA_zzz_999"
        resp = _get(api_base_url, f"/{fake}/connection")
        assert resp.status_code == 502

    def test_all_mode_missing_id_query_param_returns_5xx(self, api_base_url):
        """id_uva=all with no ?id= → handler does None.split() → AttributeError.

        Layer hit: Lambda handler (unhandled exception) -> API Gateway 502.
        """
        resp = _get(api_base_url, "/all/connection")
        assert resp.status_code >= 500

    def test_all_mode_empty_id_value_returns_502(self, api_base_url):
        """id_uva=all with empty ?id= : ''.split(',') -> [''].

        AppSync getUVA('') returns a DynamoDB error with getUVA=null, so the
        same get_creation_date crash applies -> REAL HTTP 502.
        Layer hit: Lambda handler (crash) + real AppSync (empty-key error).
        """
        resp = _get(api_base_url, "/all/connection", params={"id": ""})
        assert resp.status_code == 502

    def test_malformed_id_list_trailing_comma_returns_502(self, api_base_url):
        """'FAKE_A,' splits to ['FAKE_A', ''] -> nonexistent + empty ids.

        Both resolve to getUVA=null, so the handler crashes -> REAL HTTP 502.
        Layer hit: Lambda handler (crash) + real AppSync.
        """
        resp = _get(api_base_url, "/all/connection", params={"id": "FAKE_A,"})
        assert resp.status_code == 502

    def test_wrong_method_post_on_connection_path(self, api_base_url):
        """POST on a GET-only route is not matched by API Gateway -> 403.

        Layer hit: API Gateway routing (no integration invoked).
        """
        resp = requests.post(
            f"{api_base_url}/some-uva/connection", timeout=TIMEOUT
        )
        assert resp.status_code >= 400
        assert resp.status_code != 200

    def test_wrong_method_delete_on_connection_path(self, api_base_url):
        resp = requests.delete(
            f"{api_base_url}/some-uva/connection", timeout=TIMEOUT
        )
        assert resp.status_code >= 400
        assert resp.status_code != 200

    def test_unknown_path_returns_client_error(self, api_base_url):
        """A path that matches no route -> API Gateway 403 (missing auth token).

        Layer hit: API Gateway routing.
        """
        resp = _get(api_base_url, "/no/such/route/at/all")
        assert resp.status_code >= 400
        assert resp.status_code != 200

    def test_missing_connection_suffix_returns_client_error(self, api_base_url):
        """/{id_uva} without the /connection suffix matches no route."""
        resp = _get(api_base_url, "/just-an-id")
        assert resp.status_code >= 400
        assert resp.status_code != 200

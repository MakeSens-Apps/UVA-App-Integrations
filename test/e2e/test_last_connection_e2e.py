"""
REAL end-to-end tests for GET /{id_uva}/connection — DUAL TARGET, TRUE PARITY.

The same tests run against either target, selected by ``E2E_BASE_URL``:

  * PRODUCTION (default, ``E2E_BASE_URL`` unset →
    ``https://api.makesens.co/internal/uva-integration-main``), SigV4-signed
    (AWS_IAM), read-only GET only; or
  * LOCAL (``E2E_BASE_URL=http://127.0.0.1:3031``) via ``sam local start-api``,
    unsigned, the Lambda running in Docker and calling the SAME ``main`` AppSync.

No mocking is involved. Live UVA ids are discovered at runtime from the main
AppSync (``listUVAS``), so green cases exercise real data on both targets.

GROUND TRUTH (re-probed 2026-06-10, signed read-only role with
``lambda:InvokeFunction`` now granted on the caller-credentials integration):

  GREEN — both targets return identical HTTP 200 + shape, because both proxy the
  SAME ``main`` AppSync:
    * single live id            -> 200  {"<id>": {"connection": <bool>, "ts": <int ms>}}
    * id_uva=all + one ?id=     -> 200  {"<id>": {...}}
    * id_uva=all + many ?id=    -> 200  {"<id>": {...}, "<id2>": {...}}

  RED — honest residual handler bug, IDENTICAL on both targets:
    * unknown uva / missing ?id / empty ?id / malformed list -> 502.
      AppSync ``getUVA`` returns null; the handler does
      ``data['data']['getUVA'].get('createdAt')`` on ``None`` -> AttributeError
      (get_creation_date, last_connection.py L176) -> unhandled -> API GW 502.
      This is asserted (not forced green) and documented as a known bug.
    * wrong HTTP method / unknown path / missing suffix -> 4xx
      (prod: 403 Missing Authentication / 404 No method; local: 4xx).

HISTORICAL NOTE: phase-2 recorded prod returning 500 for every signed GET and
concluded the deployed Lambda was "stale". That was a PERMISSIONS ARTIFACT — the
internal API invokes the backend Lambda with the CALLER's credentials, and the
read-only role lacked ``lambda:InvokeFunction``. With that permission granted,
prod is fully operational and reaches true green parity with local, as the
assertions below now demand on BOTH targets without any per-target branching for
the success path.

POST ``/CreateRacimo`` WRITES and is covered exclusively at the integration tier
(``test/integration/``); it is NEVER exercised against real AWS here.
"""

import pytest

TIMEOUT = 60


def _assert_connection_value(value):
    """A per-id value is either null (no data) or {connection: bool, ts: int ms}."""
    if value is not None:
        assert isinstance(value, dict), value
        assert isinstance(value["connection"], bool), value
        assert isinstance(value["ts"], int), value


# ===========================================================================
# GREEN — combination 1: single live id  (200 + shape on BOTH targets)
# ===========================================================================
class TestSingleLiveId:
    def test_single_live_id_status(self, client, real_uva_id):
        """Live id -> HTTP 200 identically on prod and local."""
        uva = real_uva_id[0]
        resp = client.get(f"/{uva}/connection")
        assert resp.status_code == 200, resp.text

    def test_single_live_id_body_shape(self, client, real_uva_id):
        """Body is keyed solely by the requested id; value null or {connection,ts}."""
        uva = real_uva_id[0]
        resp = client.get(f"/{uva}/connection")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert uva in body
        assert len(body) == 1
        _assert_connection_value(body[uva])


# ===========================================================================
# GREEN — combination 2: id_uva=all with a single id in ?id=
# ===========================================================================
class TestAllModeSingleId:
    def test_all_single_id_status(self, client, real_uva_id):
        uva = real_uva_id[0]
        resp = client.get("/all/connection", params={"id": uva})
        assert resp.status_code == 200, resp.text

    def test_all_single_id_body(self, client, real_uva_id):
        uva = real_uva_id[0]
        resp = client.get("/all/connection", params={"id": uva})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert uva in body
        assert len(body) == 1
        _assert_connection_value(body[uva])


# ===========================================================================
# GREEN — combination 3: id_uva=all with multiple ids in ?id=
# ===========================================================================
class TestAllModeMultipleIds:
    def test_all_multiple_ids_status(self, client, real_uva_id):
        ids = real_uva_id[:2] if len(real_uva_id) >= 2 else real_uva_id
        resp = client.get("/all/connection", params={"id": ",".join(ids)})
        assert resp.status_code == 200, resp.text

    def test_all_multiple_ids_body(self, client, real_uva_id):
        ids = real_uva_id[:3] if len(real_uva_id) >= 3 else real_uva_id
        resp = client.get("/all/connection", params={"id": ",".join(ids)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for uva in ids:
            assert uva in body
            _assert_connection_value(body[uva])

    def test_all_multiple_ids_one_per_key(self, client, real_uva_id):
        """Each requested id appears exactly once; no extra keys leak in."""
        ids = real_uva_id[:2] if len(real_uva_id) >= 2 else real_uva_id
        resp = client.get("/all/connection", params={"id": ",".join(ids)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == set(ids)


# ===========================================================================
# RED — error / edge behaviour (asserting the ACTUAL running-API response)
# ===========================================================================
class TestRedCases:
    # ---- Known handler bug: getUVA->null -> None.get('createdAt') -> 502 ----
    # IDENTICAL on both targets (both hit the same AppSync). Asserted, not forced
    # green. See module docstring + docs/API_AND_TESTS.md "Known bug".

    def test_nonexistent_uva_is_502(self, client):
        """Unknown id: AppSync getUVA null -> handler AttributeError -> API GW 502.

        Same on prod and local (same AppSync, same buggy code path).
        """
        fake = "NONEXISTENT_FAKE_UVA_zzz_999"
        resp = client.get(f"/{fake}/connection")
        assert resp.status_code == 502, resp.text

    def test_nonexistent_uva_not_2xx(self, client):
        """Whatever the exact code, an unknown id never succeeds (no 2xx)."""
        fake = "NONEXISTENT_FAKE_UVA_zzz_999"
        resp = client.get(f"/{fake}/connection")
        assert resp.status_code >= 500
        assert resp.status_code != 200

    def test_all_mode_missing_id_query_param_is_502(self, client):
        """id_uva=all with no ?id= -> None.split() path -> getUVA null -> 502."""
        resp = client.get("/all/connection")
        assert resp.status_code == 502, resp.text

    def test_all_mode_empty_id_value_is_502(self, client):
        """id_uva=all with empty ?id= : ''.split(',') -> [''] -> getUVA null -> 502."""
        resp = client.get("/all/connection", params={"id": ""})
        assert resp.status_code == 502, resp.text

    def test_malformed_id_list_trailing_comma_is_502(self, client):
        """'FAKE_A,' -> ['FAKE_A',''] -> both nonexistent -> getUVA null -> 502."""
        resp = client.get("/all/connection", params={"id": "FAKE_A,"})
        assert resp.status_code == 502, resp.text

    # ---- Routing / method rejection: 4xx, never 2xx, on both targets --------

    def test_wrong_method_post_on_connection_path(self, client):
        """POST on a GET-only route is rejected (never 2xx).

        PROD: API GW returns 403 (Missing Authentication Token — no POST route).
        LOCAL: sam local returns a 4xx for the unmatched method. Either way a
        client error, never success — and POST is NEVER routed to /CreateRacimo.
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

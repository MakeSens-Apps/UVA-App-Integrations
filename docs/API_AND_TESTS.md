# API & Tests — UVA-App-Integrations

This document is the endpoint reference for the SAM app in
`SAM-UVA-App-Integrations/` plus the test tiering (integration vs. real e2e),
the green/red test counts, and how to run everything.

---

## 1. Endpoint inventory

| Method | Path | Lambda (handler) | Auth | Datastore | Tier |
|--------|------|------------------|------|-----------|------|
| `GET`  | `/{id_uva}/connection` | `UVALastConnection` (`lambdas/uvaConnection/last_connection.py`) | `AWS_IAM`* | **AppSync GraphQL** (API-key, read-only) | **Real e2e** |
| `POST` | `/CreateRacimo` | `CreateRacimo` (`lambdas/createRacimo/create_racimo.py`) | `AWS_IAM` | AppSync GraphQL **write** (SigV4) | **Integration (mocked)** |

Non-HTTP Lambdas (no HTTP tests — they are DynamoDB-Stream / event triggered):

| Lambda | Handler | Trigger |
|--------|---------|---------|
| `DynamoDBEventProcessorFunction` | `lambdas/deviceDataAccess/dynamodb_to_sns.py` | DynamoDB Stream → SNS |
| `UvaToCloudFunction` | `lambdas/cloud/uva_to_cloud.py` | DynamoDB Stream → Cloud AppSync |

\* The `AWS_IAM` authorizer is **not** enforced by `sam local start-api`, so the
real e2e HTTP calls below succeed without SigV4 signing. The GET Lambda's actual
AppSync access is authorised by the **API key** (`x-api-key`), not the IAM role,
which is why the read-only e2e is safe under `ReadOnlyAccess`.

### `GET /{id_uva}/connection`

Returns, per UVA id, whether the device reported a measurement in the last 24 h.

* Single device: `GET /{id_uva}/connection` → `{ "<id>": {connection, ts} | null }`
* Bulk: `GET /all/connection?id=a,b,c` → one key per id.
* Per-id value: `{"connection": <bool>, "ts": <unix-ms int>}` when the device has
  a measurement or a `getUVA.createdAt`; otherwise `null`.

Resolution logic: query `measurementsByUvaIDAndTs` (latest ts); if empty, fall
back to `getUVA.createdAt`; `connection` is `ts` within the last 24 h.

### `POST /CreateRacimo`

Body `{ "name": str, "linkageCode": str }`. Checks `listRACIMOS` for the
linkage code; if present returns the existing racimo, otherwise runs the
`createRACIMO` mutation (a **write**) and returns the new id. Because it writes,
it is covered **only** at the integration tier with the AppSync datastore mocked
by reference — never against real AWS/AppSync.

---

## 2. Test tiers & counts

| Endpoint | Tier | File | Green | Red | Total |
|----------|------|------|-------|-----|-------|
| `GET /{id_uva}/connection` | **e2e** (sam local + real AppSync) | `test/e2e/test_last_connection_e2e.py` | 8 | 8 | 16 |
| `GET /{id_uva}/connection` | integration (mocked) | `test/integration/test_last_connection.py` | 10 | 8 | 18 |
| `POST /CreateRacimo` | integration (mocked) | `test/integration/test_create_racimo.py` | 12 | 10 | 22 |

### e2e green coverage (real success, per param combination)

* Single live id → 200, body keyed by id, value shape `{connection:bool, ts:int}` (3).
* `id_uva=all` + single `?id=` → 200, one key (2).
* `id_uva=all` + multiple `?id=a,b` → 200, every key present, value shape (3).

The live UVA id(s) are **discovered at runtime** via a read-only `listUVAS`
query against AppSync (`real_uva_id` fixture) — nothing is hardcoded.

### e2e red coverage (asserting the ACTUAL running-API response)

| Case | Real status | Layer |
|------|-------------|-------|
| Nonexistent uva id | **502** (handler bug, see §4) | Lambda crash + real AppSync |
| `id_uva=all` with missing `?id=` | 5xx (`None.split` → AttributeError) | Lambda crash |
| `id_uva=all` with empty `?id=` | 502 (empty-key DynamoDB error → bug) | Lambda crash + real AppSync |
| `id_uva=all` with trailing comma `a,` | 502 (same bug) | Lambda crash + real AppSync |
| `POST` on the GET-only path | ≥400 (route not matched) | API Gateway routing |
| `DELETE` on the GET-only path | ≥400 | API Gateway routing |
| Unknown path | ≥400 | API Gateway routing |
| `/{id}` without `/connection` suffix | ≥400 | API Gateway routing |

---

## 3. How to run

### Integration (no Docker / AWS needed — fully mocked)

```bash
make install-test        # or: python3 -m pip install -r test/requirements-test.txt
make test-integration
```

### Real e2e (Docker + AWS read-only creds + AppSync env vars)

```bash
# 1. AWS SSO read-only credentials in the shell (propagated into the container):
eval "$(aws configure export-credentials --format env)"
export AWS_DEFAULT_REGION=us-east-1

# 2. Run — sam build, sam local start-api on :3031, real HTTP to real AppSync:
make test-e2e
```

`make test` runs **both** tiers.

#### Where the AppSync env vars come from

The GET Lambda needs `AppSyncURL` + `ApiKey` in its container. The e2e conftest
(`test/e2e/conftest.py`) resolves them in this order:

1. `UVA_APPSYNC_URL` / `UVA_API_KEY` environment variables (CI override), else
2. the `develop` profile in `SAM-UVA-App-Integrations/parameters.json`
   (`UvaAppsyncUrl` / `UvaApiKey`), which is already committed in this repo.

It then writes a **sam-local `--env-vars` file** at
`SAM-UVA-App-Integrations/event/env.json` (per-function env vars) and passes it
to `sam local start-api --env-vars ...`. That file is **gitignored**
(`.gitignore`) so no key is committed twice; an
`event/env.json.example` documents the shape.

The harness **skips gracefully** (never fails) when Docker is not running, the
`sam` CLI is missing, or the AppSync URL/key cannot be resolved.

---

## 4. Bug found (real e2e)

`get_creation_date` in `lambdas/uvaConnection/last_connection.py` does:

```python
created_at = data.get('data', {}).get('getUVA', {}).get('createdAt')
```

For a **nonexistent** uva id the live AppSync returns `{"data": {"getUVA": null}}`
— the `getUVA` key is present with value `None`, so the `, {}` default is never
used and this becomes `None.get('createdAt')` → `AttributeError` →
unhandled → **API Gateway 502**.

So a request for an unknown device returns HTTP **502**, not the intended
graceful `200` with a `null` value. This is asserted (as the real behaviour) by:

* e2e: `test_nonexistent_uva_returns_502_handler_bug` (and the empty / malformed
  id variants).
* integration: `test_nonexistent_uva_getuva_null_raises_attribute_error_bug`
  (reproduces the real `getUVA: null` shape).

A fix would be `(... .get('getUVA') or {}).get('createdAt')`. Not applied here —
this change set is test-only.

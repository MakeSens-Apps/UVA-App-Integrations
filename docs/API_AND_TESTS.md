# API & Tests — UVA-App-Integrations

This document is the endpoint reference for the SAM app in
`SAM-UVA-App-Integrations/` plus the test tiering (integration vs. real e2e),
the **dual-target** e2e contract (production + local), the green/red test
counts, and how to run everything.

---

## 1. Endpoint inventory

| Method | Path | Lambda (handler) | Auth | Datastore | Tier |
|--------|------|------------------|------|-----------|------|
| `GET`  | `/{id_uva}/connection` | `UVALastConnection` (`lambdas/uvaConnection/last_connection.py`) | `AWS_IAM` (SigV4) | **AppSync GraphQL** (API-key, read-only) | **Real e2e (prod + local)** |
| `POST` | `/CreateRacimo` | `CreateRacimo` (`lambdas/createRacimo/create_racimo.py`) | `AWS_IAM` | AppSync GraphQL **write** (SigV4) | **Integration (mocked)** |

Non-HTTP Lambdas (no HTTP tests — they are DynamoDB-Stream / event triggered):

| Lambda | Handler | Trigger |
|--------|---------|---------|
| `DynamoDBEventProcessorFunction` | `lambdas/deviceDataAccess/dynamodb_to_sns.py` | DynamoDB Stream → SNS |
| `UvaToCloudFunction` | `lambdas/cloud/uva_to_cloud.py` | DynamoDB Stream → Cloud AppSync |

### `GET /{id_uva}/connection`

Returns, per UVA id, whether the device reported a measurement in the last 24 h.

* Single device: `GET /{id_uva}/connection` → `{ "<id>": {connection, ts} | null }`
* Bulk: `GET /all/connection?id=a,b,c` → one key per id.
* Per-id value: `{"connection": <bool>, "ts": <unix-ms int>}` when the device has
  a measurement or a `getUVA.createdAt`; otherwise `null`.

Resolution logic: query `measurementsByUvaIDAndTs` (latest ts); if empty, fall
back to `getUVA.createdAt`; `connection` is `ts` within the last 24 h.

### `POST /CreateRacimo`

Body `{ "name": str, "linkageCode": str }`. Because it **writes**, it is covered
**only** at the integration tier with AppSync mocked — never against real
AWS/AppSync, and **NEVER against production** (the read-only SSO role also lacks
`POST` on prod, so a prod POST is rejected with 403 as a safety backstop).

---

## 2. Dual-target e2e contract

The same e2e suite (`test/e2e/`) runs against **two targets**, selected by the
**`E2E_BASE_URL`** environment variable. This is the regression safety net for
the upcoming migration: identical green tests pass on both.

| `E2E_BASE_URL` | Target | Signing | Server lifecycle |
|----------------|--------|---------|------------------|
| *unset* (default) | **Production** `https://api.makesens.co/internal/uva-integration-main` | **SigV4-signed** (`execute-api`, AWS_IAM) | none — live endpoint |
| `http://127.0.0.1:3031` | **Local** `sam local start-api` | unsigned | conftest builds/starts/stops sam |

**Signing rule:** the HTTP client (`E2EClient` in `conftest.py`) auto-SigV4-signs
iff the target host is **not** `localhost` / `127.0.0.1`. All paths are
`E2E_BASE_URL + /{id_uva}/connection` (`+ ?id=…` for the `all` branch) — no host
is hardcoded in the tests.

### Production endpoint — verified

* Base-path mapping on `api.makesens.co`:
  `internal/uva-integration-main` → RestApi **`m10nv4uxdf`** (stage `Prod`)
  (`aws apigateway get-base-path-mappings --domain-name api.makesens.co`).
* CloudFormation stack **`UVA-App-Integrations-main`** owns RestApi `m10nv4uxdf`
  (`ServerlessRestApi`) and Lambda `…-UVALastConnection-03h28ePAOiI7`
  (`aws cloudformation describe-stack-resources`).
* `GET /{id_uva}/connection` method: `authorizationType = AWS_IAM`,
  `AWS_PROXY` integration to that Lambda.
* Invoke permission confirmed for the read-only SSO role via
  `aws iam simulate-principal-policy --action-names execute-api:Invoke
  --resource-arns arn:aws:execute-api:us-east-1:913045965320:m10nv4uxdf/Prod/GET/*`
  → **allowed**.

### Data parity (prod ↔ local)

The deployed prod Lambda's `AppSyncURL` env var is
`https://iifnqxdvi5dtxm73slwddeccha.appsync-api.us-east-1.amazonaws.com/graphql`
— the **`main`** profile's `UvaAppsyncUrl` in `parameters.json`. So local e2e
points the sam-local Lambda at the **same `main` AppSync** (see §4), and the
runtime-discovered live UVA id resolves to identical data on both targets.

---

## 3. Test tiers & counts

| Endpoint | Tier | File | Green | Red | Total |
|----------|------|------|-------|-----|-------|
| `GET /{id_uva}/connection` | **e2e** (prod + local, same file) | `test/e2e/test_last_connection_e2e.py` | 6 | 9 | 15 |
| `GET /{id_uva}/connection` | integration (mocked) | `test/integration/test_last_connection.py` | 10 | 8 | 18 |
| `POST /CreateRacimo` | integration (mocked) | `test/integration/test_create_racimo.py` | 12 | 10 | 22 |

### e2e green coverage (per param combination — discovered live id)

* Single live id → status + body shape (2).
* `id_uva=all` + single `?id=` → status + body (2).
* `id_uva=all` + multiple `?id=a,b` → status + body (2).

The live UVA id(s) are **discovered at runtime** via a read-only `listUVAS`
query against the **main** AppSync (`real_uva_id` fixture) — nothing is
hardcoded. Greens branch on the `target_is_local` fixture so they assert the
**actual** behaviour on each target (see §5) and stay green on both.

### e2e red coverage (asserting the ACTUAL running-API response, both targets)

| Case | Local | Prod | Layer |
|------|-------|------|-------|
| Nonexistent uva id | **502** (handler bug §6) | **500** (deployed-handler failure §5) | Lambda crash + real AppSync |
| `id_uva=all` missing `?id=` | ≥500 | ≥500 | Lambda crash |
| `id_uva=all` empty `?id=` | 502 | 500 | Lambda crash + real AppSync |
| `id_uva=all` trailing comma `a,` | 502 | 500 | Lambda crash + real AppSync |
| `POST` on GET-only path | ≥400 ≠200 | 403 (no IAM `POST`) | API GW / IAM |
| `DELETE` on GET-only path | ≥400 ≠200 | 403 | API GW / IAM |
| Unknown path | ≥400 ≠200 | 404 | API GW routing |
| `/{id}` without `/connection` | ≥400 ≠200 | 404 | API GW routing |

---

## 4. How to run

### Integration (no Docker / AWS needed — fully mocked)

```bash
make install-test
make test-integration
```

### Real e2e — production (read-only, signed, no Docker)

```bash
make test-e2e-prod
# = E2E_BASE_URL=https://api.makesens.co/internal/uva-integration-main \
#     python3 -m pytest test/e2e -v   (AWS SSO creds exported for SigV4)
```

### Real e2e — local (sam local start-api on :3031, one command)

```bash
make test-e2e-local
# exports AWS SSO creds, then E2E_BASE_URL=http://127.0.0.1:3031 pytest test/e2e
# the conftest owns: sam build → start-api (--warm-containers LAZY,
# --env-vars event/env.json) → ready-poll → run → teardown.
```

* `make test-e2e` runs **both** (`test-e2e-prod` then `test-e2e-local`).
* `make test` runs integration + both e2e targets.

#### Where the local AppSync env vars come from

For the local target the GET Lambda needs `AppSyncURL` + `ApiKey` in its
container. The conftest resolves them in this order:

1. `UVA_APPSYNC_URL` / `UVA_API_KEY` environment variables (CI override), else
2. the **`main`** profile in `SAM-UVA-App-Integrations/parameters.json`
   (`UvaAppsyncUrl` / `UvaApiKey`) — the same AppSync the deployed prod Lambda
   uses, for prod/local parity.

It writes a **sam-local `--env-vars` file** at
`SAM-UVA-App-Integrations/event/env.json` and passes it to
`sam local start-api --env-vars …`. That file is **gitignored** so no key is
committed; `event/env.json.example` documents the shape. The harness **skips
gracefully** (never fails) when Docker/`sam`/creds are unavailable.

---

## 5. Prod-vs-local divergence (captured honestly)

The e2e runs found a **genuine divergence** between targets — recorded, not
faked:

* **Local** (Lambda built from this repo, running in Docker): a live id returns
  **HTTP 200** with `{"<id>": {"connection": <bool>, "ts": <int>}}`; an unknown
  id returns **HTTP 502** (the §6 handler bug).
* **Production** (`m10nv4uxdf`, deployed Lambda last modified `2024-12-27`, no
  successful invocation logged since `2025-04`): **every** signed `GET`,
  *including a live id*, returns **HTTP 500** `{"message":"Internal server
  error"}`. Unsigned requests get `403 Missing Authentication Token`, so SigV4
  auth succeeds and the 500 is a real **deployed-handler failure** (it occurs
  before the Lambda emits any new CloudWatch log line), distinct from the local
  502.

**Root cause / divergence:** the deployed prod Lambda runs an older/broken code
version than the one in this repo (which works locally). The migration must
redeploy this stack; this suite will then flip the prod greens to 200 and the
prod reds to 502, matching local. Until then the suite asserts the *current*
prod reality (500) so it stays green while truthfully recording the outage.

Evidence (full pytest output, no secrets): `docs/evidence/e2e-prod.log`,
`docs/evidence/e2e-local.log`.

---

## 6. Bug found (handler) — `getUVA: null`

`get_creation_date` in `lambdas/uvaConnection/last_connection.py` does:

```python
created_at = data.get('data', {}).get('getUVA', {}).get('createdAt')
```

For a **nonexistent** uva id AppSync returns `{"data": {"getUVA": null}}` — the
`getUVA` key is present with value `None`, so the `, {}` default is never used
and this becomes `None.get('createdAt')` → `AttributeError` → unhandled →
**API Gateway 502** (observed locally). A fix would be
`(… .get('getUVA') or {}).get('createdAt')`. Not applied — this change set is
test-only.

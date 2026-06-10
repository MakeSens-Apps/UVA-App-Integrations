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
* **Caller-credentials note:** the integration invokes the Lambda *as the
  caller*, so the signing principal also needs **`lambda:InvokeFunction`** on
  `UVA-App-Integrations-main-UVALastConnection-*`. This was missing in phase-2
  (producing a misleading 500) and has since been **granted** — prod now returns
  real `200` (see §5).

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
| `GET /{id_uva}/connection` | **e2e** (prod + local, same file) | `test/e2e/test_last_connection_e2e.py` | 7 | 9 | 16 |
| `GET /{id_uva}/connection` | integration (mocked) | `test/integration/test_last_connection.py` | 10 | 8 | 18 |
| `POST /CreateRacimo` | integration (mocked) | `test/integration/test_create_racimo.py` | 12 | 10 | 22 |

### e2e green coverage (per param combination — discovered live id)

* Single live id → status + body shape (2).
* `id_uva=all` + single `?id=` → status + body (2).
* `id_uva=all` + multiple `?id=a,b` → status + body + one-key-per-id (3).

The live UVA id(s) are **discovered at runtime** via a read-only `listUVAS`
query against the **main** AppSync (`real_uva_id` fixture) — nothing is
hardcoded. The greens assert **identical** `200` + per-id `{connection, ts}`
shape on **both** prod and local with **no per-target branching** — true green
parity (see §5).

### Prod-vs-local green parity (both assert the SAME result)

| Combination | Prod | Local | Assertion |
|-------------|------|-------|-----------|
| Single live id | **200** `{"<id>":{connection,ts}}` | **200** (identical) | `status==200`, single key, value null or `{bool,int}` |
| `all` + single `?id=` | **200** | **200** (identical) | `status==200`, single key |
| `all` + multiple `?id=a,b` | **200** | **200** (identical) | `status==200`, one key per id, shape, `keys==set(ids)` |

Both targets proxy the **same** `main` AppSync, so the runtime-discovered live id
returns the same underlying data and the suite is green on both with the same
assertions.

### e2e red coverage (asserting the ACTUAL running-API response — same on both)

| Case | Prod | Local | Layer |
|------|------|-------|-------|
| Nonexistent uva id | **502** (handler bug §6) | **502** (handler bug §6) | Lambda crash + real AppSync |
| `id_uva=all` missing `?id=` | **502** | **502** | Lambda crash |
| `id_uva=all` empty `?id=` | **502** | **502** | Lambda crash + real AppSync |
| `id_uva=all` trailing comma `a,` | **502** | **502** | Lambda crash + real AppSync |
| `POST` on GET-only path | 403 (no IAM `POST`) | ≥400 ≠200 | API GW / IAM |
| `DELETE` on GET-only path | 403 | ≥400 ≠200 | API GW / IAM |
| Unknown path | 404 | ≥400 ≠200 | API GW routing |
| `/{id}` without `/connection` | 404 | ≥400 ≠200 | API GW routing |

The `502` residual is **identical on both targets** (same AppSync, same handler
code path) — asserted, not forced green, and documented as a known bug in §6.

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

## 5. Prod is operational — green parity with local

> **Correction of a prior (phase-2) conclusion.** An earlier run reported that
> **every** signed prod `GET` — *including a live id* — returned **HTTP 500**
> `{"message":"Internal server error"}`, and concluded the deployed prod Lambda
> was "stale/broken". **That was wrong.** It was a **permissions artifact**, not
> a code failure.
>
> The internal API (`internal/uva-integration-main`) invokes the backend Lambda
> with **caller credentials** (the integration runs the Lambda *as the signing
> principal*). The read-only SSO role used for testing had `execute-api:Invoke`
> on the API Gateway method but **lacked `lambda:InvokeFunction`** on
> `UVA-App-Integrations-main-UVALastConnection-*`. So SigV4 reached API Gateway,
> but the caller-credentials invocation of the Lambda was denied → API Gateway
> surfaced a generic **500**. The 500 was authorization, not a handler crash.
>
> That permission has now been **granted**. Re-probed (signed, read-only role):
>
> ```
> GET https://api.makesens.co/internal/uva-integration-main/UVA_ANT025_00017/connection
>   → 200 {"UVA_ANT025_00017": {"connection": true, "ts": 1781094352298}}
> ```

**Prod is therefore healthy and reaches true green parity with local.** Both
targets proxy the **same** `main` AppSync, so:

* **GREEN** — single live id, `all`+single `?id=`, and `all`+multiple `?id=` all
  return **HTTP 200** with `{"<id>": {"connection": <bool>, "ts": <int ms>}}` on
  **both** prod and local. The e2e greens assert this **identically** on both
  targets with **no per-target branching** (see §3 parity table).
* **RED residual** — an unknown id (and the missing/empty/malformed `?id=`
  variants that resolve to an unknown id) returns **HTTP 502** on **both**
  targets, because both hit the same AppSync and the same handler code path (the
  §6 `getUVA: null` bug). This is asserted as the real status on each target, not
  forced green, and documented as a known bug.

Evidence (full pytest output, no secrets): `docs/evidence/e2e-prod.log`,
`docs/evidence/e2e-local.log` — both **16 passed**.

---

## 6. Bug found (handler) — `getUVA: null`

`get_creation_date` in `lambdas/uvaConnection/last_connection.py` does:

```python
created_at = data.get('data', {}).get('getUVA', {}).get('createdAt')
```

For a **nonexistent** uva id AppSync returns `{"data": {"getUVA": null}}` — the
`getUVA` key is present with value `None`, so the `, {}` default is never used
and this becomes `None.get('createdAt')` → `AttributeError` → unhandled →
**API Gateway 502**. This is observed **identically on both prod and local**
(same AppSync, same handler code), so it is a genuine product bug, not a
prod/local divergence. A fix would be `(… .get('getUVA') or {}).get('createdAt')`.
Not applied — this change set is test-only.

"""
Real end-to-end test harness for UVA-App-Integrations — DUAL TARGET.

The same suite runs against TWO targets, selected by the ``E2E_BASE_URL``
environment variable:

  * ``E2E_BASE_URL`` UNSET (default) → PRODUCTION:
    ``https://api.makesens.co/internal/uva-integration-main`` (apiId
    ``m10nv4uxdf``, stack ``UVA-App-Integrations-main``). Auth = AWS_IAM, so
    requests are SigV4-signed with the caller's AWS credentials. Read-only GETs
    only — the suite NEVER POSTs to prod.

  * ``E2E_BASE_URL=http://127.0.0.1:3031`` → LOCAL ``sam local start-api``.
    The Lambda runs in Docker and makes REAL calls to the SAME (main) AppSync
    used by prod, so the two targets point at identical data. Local requests are
    sent UNSIGNED (sam local does not enforce IAM auth).

Signing rule: the HTTP client auto-SigV4-signs iff the target host is NOT
``localhost`` / ``127.0.0.1``.

Parity: both prod and local invoke the SAME ``main`` AppSync GraphQL API, so a
live UVA id discovered at runtime (read-only ``listUVAS``) returns the same
underlying data on both targets. NOTE: the deployed prod Lambda and the locally
built Lambda may run *different code versions* — divergences are captured
honestly by the tests (see ``E2E_TARGET_IS_LOCAL`` branches), never faked.

POST ``/CreateRacimo`` WRITES and is covered exclusively at the integration
tier (``test/integration/``); it is never exercised against real AWS here.
"""

import json
import os
import shutil
import signal
import subprocess
import time
from urllib.parse import urlsplit

import pytest

try:
    import requests
except ImportError:  # pragma: no cover - requests is a declared test dep
    requests = None


# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAM_DIR = os.path.join(REPO_ROOT, "SAM-UVA-App-Integrations")
PARAMETERS_JSON = os.path.join(SAM_DIR, "parameters.json")
ENV_VARS_FILE = os.path.join(SAM_DIR, "event", "env.json")  # generated, gitignored

# Production endpoint (verified: base-path mapping internal/uva-integration-main
# on api.makesens.co -> RestApi m10nv4uxdf -> stack UVA-App-Integrations-main).
PROD_BASE_URL = "https://api.makesens.co/internal/uva-integration-main"

API_PORT = 3031
LOCAL_BASE_URL = f"http://127.0.0.1:{API_PORT}"
LAST_CONNECTION_FUNCTION = "UVALastConnection"
READY_TIMEOUT_SECONDS = 120

# Both targets must point at the SAME AppSync for data parity. Prod's deployed
# Lambda uses the ``main`` profile's UvaAppsyncUrl/UvaApiKey, so local does too.
APPSYNC_PROFILE = os.environ.get("UVA_PARAM_PROFILE", "main")

AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
AWS_SERVICE = "execute-api"


# ---------------------------------------------------------------------------
# Target resolution + signing
# ---------------------------------------------------------------------------
def _resolve_base_url() -> str:
    return os.environ.get("E2E_BASE_URL", PROD_BASE_URL).rstrip("/")


def _is_localhost(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def _sigv4_headers(method, url, params, region=AWS_REGION, service=AWS_SERVICE):
    """Build SigV4 Authorization headers for a GET to API Gateway (AWS_IAM)."""
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    import botocore.session

    if params:
        from urllib.parse import urlencode

        url = url + ("&" if "?" in url else "?") + urlencode(params)

    session = botocore.session.get_session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError("No AWS credentials available for SigV4 signing.")
    creds = creds.get_frozen_credentials()

    aws_req = AWSRequest(method=method, url=url)
    SigV4Auth(creds, service, region).add_auth(aws_req)
    return dict(aws_req.headers), url


class E2EClient:
    """HTTP client that auto-SigV4-signs non-localhost (prod) requests."""

    def __init__(self, base_url, timeout=60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.is_local = _is_localhost(self.base_url)

    def get(self, path, params=None):
        url = f"{self.base_url}{path}"
        if self.is_local:
            return requests.get(url, params=params, timeout=self.timeout)
        headers, signed_url = _sigv4_headers("GET", url, params)
        prepared = requests.Request("GET", signed_url, headers=headers).prepare()
        return requests.Session().send(prepared, timeout=self.timeout)

    def request(self, method, path, params=None):
        """Generic request (used for negative method tests). Signs for prod."""
        url = f"{self.base_url}{path}"
        if self.is_local:
            return requests.request(method, url, params=params, timeout=self.timeout)
        headers, signed_url = _sigv4_headers(method, url, params)
        prepared = requests.Request(method, signed_url, headers=headers).prepare()
        return requests.Session().send(prepared, timeout=self.timeout)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _docker_running() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "ps"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _resolve_appsync_env():
    """Resolve (AppSyncURL, ApiKey) for the UVALastConnection Lambda.

    Order of precedence:
      1. UVA_APPSYNC_URL / UVA_API_KEY environment variables (CI / override).
      2. The ``main`` profile in the committed parameters.json — the SAME
         AppSync the deployed prod Lambda uses, ensuring prod/local parity.
    Returns (url, key) or (None, None) if neither source is available.
    """
    url = os.environ.get("UVA_APPSYNC_URL")
    key = os.environ.get("UVA_API_KEY")
    if url and key:
        return url, key

    try:
        with open(PARAMETERS_JSON, "r", encoding="utf-8") as fh:
            params = json.load(fh)
        overrides = params[APPSYNC_PROFILE]["parameter_overrides"]
        return overrides.get("UvaAppsyncUrl"), overrides.get("UvaApiKey")
    except Exception:
        return None, None


def _write_env_vars_file(appsync_url: str, api_key: str) -> str:
    """Write the sam-local --env-vars file (per-function env vars)."""
    os.makedirs(os.path.dirname(ENV_VARS_FILE), exist_ok=True)
    payload = {
        LAST_CONNECTION_FUNCTION: {
            "AppSyncURL": appsync_url,
            "ApiKey": api_key,
        }
    }
    with open(ENV_VARS_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return ENV_VARS_FILE


def _wait_until_ready(timeout: int) -> bool:
    """Poll the local API until it answers (any HTTP status) or timeout."""
    deadline = time.time() + timeout
    probe = f"{LOCAL_BASE_URL}/UVA_NAT001_00000/connection"
    while time.time() < deadline:
        try:
            requests.get(probe, timeout=10)
            return True
        except requests.exceptions.RequestException:
            time.sleep(2)
    return False


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def target_is_local():
    """True iff the suite is pointed at a localhost target."""
    return _is_localhost(_resolve_base_url())


@pytest.fixture(scope="session")
def api_base_url():
    """Resolve the target base URL.

    For a localhost target, this fixture OWNS the ``sam local start-api``
    lifecycle (build, env-vars, start, ready-poll, teardown). For a non-local
    (prod) target it simply returns the configured URL — nothing is launched.
    Skips gracefully when prerequisites are missing.
    """
    if requests is None:
        pytest.skip("'requests' library not installed — cannot run e2e HTTP tests.")

    base_url = _resolve_base_url()

    # ---- Prod / remote target: no local server to manage ------------------
    if not _is_localhost(base_url):
        # Verify credentials exist for SigV4 signing; skip honestly if not.
        try:
            import botocore.session

            if botocore.session.get_session().get_credentials() is None:
                pytest.skip(
                    "No AWS credentials available to SigV4-sign prod requests."
                )
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Could not initialise AWS credentials: {exc}")
        yield base_url
        return

    # ---- Local target: manage sam local start-api -------------------------
    if shutil.which("sam") is None:
        pytest.skip("AWS SAM CLI ('sam') not found on PATH — skipping local e2e.")

    if not _docker_running():
        pytest.skip("Docker is not running (docker ps failed) — skipping local e2e.")

    appsync_url, api_key = _resolve_appsync_env()
    if not appsync_url or not api_key:
        pytest.skip(
            "AppSync URL / API key unavailable (no UVA_APPSYNC_URL/UVA_API_KEY "
            "env vars and parameters.json could not be read) — skipping local e2e."
        )

    # 1. sam build
    build = subprocess.run(
        ["sam", "build"],
        cwd=SAM_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if build.returncode != 0:
        pytest.skip(f"`sam build` failed, skipping local e2e:\n{build.stdout[-2000:]}")

    # 2. env-vars file (main profile -> same AppSync as prod)
    env_file = _write_env_vars_file(appsync_url, api_key)

    # 3. start-api as a background process group (inherits exported AWS creds)
    proc = subprocess.Popen(
        [
            "sam",
            "local",
            "start-api",
            "--port",
            str(API_PORT),
            "--warm-containers",
            "LAZY",
            "--env-vars",
            env_file,
        ],
        cwd=SAM_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,  # own process group for clean teardown
    )

    try:
        if not _wait_until_ready(READY_TIMEOUT_SECONDS):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                pass
            out = ""
            try:
                out = proc.communicate(timeout=5)[0] or ""
            except Exception:
                pass
            pytest.skip(
                "sam local start-api did not become ready within "
                f"{READY_TIMEOUT_SECONDS}s — skipping local e2e.\n{out[-2000:]}"
            )

        yield LOCAL_BASE_URL

    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=20)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass


@pytest.fixture(scope="session")
def client(api_base_url):
    """HTTP client bound to the resolved target (auto-signs for prod)."""
    return E2EClient(api_base_url)


@pytest.fixture(scope="session")
def real_uva_id():
    """Discover live UVA ids by querying the MAIN AppSync read-only (listUVAS).

    Both targets hit this same AppSync, so these ids return real data on both.
    Skips if the AppSync env can't be resolved or the query returns no devices.
    """
    if requests is None:
        pytest.skip("'requests' library not installed.")
    appsync_url, api_key = _resolve_appsync_env()
    if not appsync_url or not api_key:
        pytest.skip("AppSync URL / API key unavailable — cannot discover a UVA id.")

    query = {"query": "query { listUVAS(limit: 5) { items { id } } }"}
    try:
        resp = requests.post(
            appsync_url,
            headers={"Content-Type": "application/json", "x-api-key": api_key},
            json=query,
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        pytest.skip(f"Could not reach AppSync to discover a UVA id: {exc}")

    if resp.status_code != 200:
        pytest.skip(f"AppSync listUVAS returned {resp.status_code} — cannot discover id.")

    items = resp.json().get("data", {}).get("listUVAS", {}).get("items", [])
    ids = [it["id"] for it in items if it.get("id")]
    if not ids:
        pytest.skip("AppSync returned no live UVA ids — cannot run green e2e.")
    return ids

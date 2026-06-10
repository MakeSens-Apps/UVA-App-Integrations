"""
Real end-to-end test harness for UVA-App-Integrations.

This conftest owns a *session-scoped* fixture that:

  1. Runs ``sam build`` inside ``SAM-UVA-App-Integrations/``.
  2. Builds a sam-local ``--env-vars`` file containing the AppSync URL + API key
     for the ``UVALastConnection`` Lambda. The values are read from the committed
     ``SAM-UVA-App-Integrations/parameters.json`` ``develop`` profile (so no new
     secret is introduced) unless overridden via the ``UVA_APPSYNC_URL`` /
     ``UVA_API_KEY`` environment variables.
  3. Starts ``sam local start-api --port 3031 --warm-containers LAZY
     --env-vars <file>`` as a background subprocess, inheriting the AWS
     credentials exported into the environment.
  4. Polls the local API until it is ready (~120 s budget), yields the base URL.
  5. Terminates the whole process group on teardown.

The fixture calls ``pytest.skip(...)`` gracefully when the environment cannot
support a real run (Docker not running, ``sam`` CLI missing, or the AppSync
URL / API key cannot be resolved). Tests that need the local API depend on the
``api_base_url`` fixture and are therefore skipped together.

Only the GET ``/{id_uva}/connection`` endpoint is exercised end-to-end here:
it is read-only against AppSync (authorised by the API key, not the IAM role).
POST ``/CreateRacimo`` WRITES and is covered exclusively at the integration
tier (see ``test/integration/``) — it is never run against real AWS/AppSync.
"""

import json
import os
import shutil
import signal
import subprocess
import time

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

API_PORT = 3031
API_BASE_URL = f"http://127.0.0.1:{API_PORT}"
LAST_CONNECTION_FUNCTION = "UVALastConnection"
READY_TIMEOUT_SECONDS = 120


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
      2. The ``develop`` profile in the committed parameters.json.
    Returns (url, key) or (None, None) if neither source is available.
    """
    url = os.environ.get("UVA_APPSYNC_URL")
    key = os.environ.get("UVA_API_KEY")
    if url and key:
        return url, key

    try:
        with open(PARAMETERS_JSON, "r", encoding="utf-8") as fh:
            params = json.load(fh)
        overrides = params["develop"]["parameter_overrides"]
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
    probe = f"{API_BASE_URL}/UVA_NAT001_00000/connection"
    while time.time() < deadline:
        try:
            requests.get(probe, timeout=10)
            return True
        except requests.exceptions.RequestException:
            time.sleep(2)
    return False


# ---------------------------------------------------------------------------
# Session-scoped fixture: real sam local start-api
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def api_base_url():
    if requests is None:
        pytest.skip("'requests' library not installed — cannot run e2e HTTP tests.")

    if shutil.which("sam") is None:
        pytest.skip("AWS SAM CLI ('sam') not found on PATH — skipping e2e.")

    if not _docker_running():
        pytest.skip("Docker is not running (docker ps failed) — skipping e2e.")

    appsync_url, api_key = _resolve_appsync_env()
    if not appsync_url or not api_key:
        pytest.skip(
            "AppSync URL / API key unavailable (no UVA_APPSYNC_URL/UVA_API_KEY "
            "env vars and parameters.json could not be read) — skipping e2e."
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
        pytest.skip(f"`sam build` failed, skipping e2e:\n{build.stdout[-2000:]}")

    # 2. env-vars file
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
        # 4. wait until ready
        if not _wait_until_ready(READY_TIMEOUT_SECONDS):
            # capture whatever output we have for diagnostics
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
                f"{READY_TIMEOUT_SECONDS}s — skipping e2e.\n{out[-2000:]}"
            )

        yield API_BASE_URL

    finally:
        # 5. terminate the process group
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=20)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Session-scoped fixture: discover a real, live UVA id from AppSync (read-only)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def real_uva_id():
    """Discover a live UVA id by querying AppSync read-only (listUVAS).

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

    items = (
        resp.json().get("data", {}).get("listUVAS", {}).get("items", [])
    )
    ids = [it["id"] for it in items if it.get("id")]
    if not ids:
        pytest.skip("AppSync returned no live UVA ids — cannot run green e2e.")
    return ids

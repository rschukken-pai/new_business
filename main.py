"""
Cloud Run function: get_new_business

Returns new-business records for a given patient from the configured
BigQuery project/dataset/table.

No project name, dataset, table, or API key is hardcoded anywhere in this
file (or in README.md) -- every one of those lives only in credentials.py
(local dev, gitignored/gcloudignored) or in the deployed service's
environment variables/secrets. See credentials.py.example for the required
names, and README.md for the deploy command.

Auth: in production this service is deployed --allow-unauthenticated at
the Cloud Run layer (so third-party tools that can't mint GCP identity
tokens, e.g. Pabbly Connect, can call it directly) but every request must
carry a shared secret, either as an `X-API-Key` header or an `api_key`
query/body param, matching the API_KEY config value. Requests without it
get 401.

Call it with either:
  GET  https://<run-url>?patient_id=<id>&api_key=<key>
  POST https://<run-url>   body: {"patient_id": "<id>", "api_key": "<key>"}
       (or send the key as the X-API-Key header instead of in the body)

Config/secrets resolution -- PROJECT_ID, DATASET, TABLE, and API_KEY are
all resolved the same way, in this order:
  1. Environment variable, if set (this is what Cloud Run uses in
     production, via --set-env-vars / --set-secrets)
  2. Otherwise, credentials.py, if present (local dev only -- this file
     is gitignored/gcloudignored and never deployed)
There is no third fallback: if a value isn't set either way, the request
fails closed (500) rather than silently running against a default.
"""

import json
import os

import functions_framework
from flask import jsonify
from google.cloud import bigquery

try:
    import credentials  # local dev only -- see credentials.py.example
except ImportError:
    credentials = None


def _config(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if credentials is not None and getattr(credentials, name, None):
        return getattr(credentials, name)
    return None


PROJECT_ID = _config("PROJECT_ID")
DATASET = _config("DATASET")
TABLE = _config("TABLE")
API_KEY = _config("API_KEY")

_REQUIRED_CONFIG = {
    "PROJECT_ID": PROJECT_ID,
    "DATASET": DATASET,
    "TABLE": TABLE,
    "API_KEY": API_KEY,
}


def _missing_config() -> list[str]:
    return [name for name, value in _REQUIRED_CONFIG.items() if not value]


def _query() -> str:
    # `patient` on the configured table holds Cliniko patient IDs, which
    # are large integers -- bind as INT64, not STRING.
    return """
SELECT *
FROM `{project}.{dataset}.{table}` AS NB
WHERE NB.patient = @patient_id
""".format(project=PROJECT_ID, dataset=DATASET, table=TABLE)


_client = None


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT_ID)
    return _client


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


@functions_framework.http
def get_new_business(request):
    """HTTP entry point for the Cloud Run function.

    Args:
        request (flask.Request): the request object.
    Returns:
        JSON: {"patient_id": ..., "count": ..., "results": [...]}
    """
    if request.method == "OPTIONS":
        return ("", 204, {**_cors_headers(), "Access-Control-Max-Age": "3600"})

    headers = _cors_headers()

    if request.method == "GET":
        raw_patient_id = request.args.get("patient_id")
        supplied_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    elif request.method == "POST":
        body = request.get_json(silent=True) or {}
        raw_patient_id = body.get("patient_id") or request.args.get("patient_id")
        supplied_key = (
            request.headers.get("X-API-Key")
            or body.get("api_key")
            or request.args.get("api_key")
        )
    else:
        return (jsonify({"error": "Method not allowed"}), 405, headers)

    missing = _missing_config()
    if missing:
        # Fail closed: an endpoint returning patient data should never run
        # with a name -- not the value -- of what's unset, so nothing
        # sensitive leaks into logs/responses either way.
        return (
            jsonify({"error": "Server misconfigured", "missing": missing}),
            500,
            headers,
        )

    if not supplied_key or supplied_key != API_KEY:
        return (jsonify({"error": "Unauthorized"}), 401, headers)

    if raw_patient_id is None or str(raw_patient_id).strip() == "":
        return (jsonify({"error": "Missing required parameter: patient_id"}), 400, headers)

    try:
        patient_id = int(raw_patient_id)
    except (TypeError, ValueError):
        return (
            jsonify({"error": "patient_id must be an integer (Cliniko patient ID)"}),
            400,
            headers,
        )

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("patient_id", "INT64", patient_id),
        ]
    )

    try:
        query_job = _get_client().query(_query(), job_config=job_config)
        rows = [dict(row) for row in query_job.result()]
    except Exception as exc:  # noqa: BLE001
        return (jsonify({"error": "Query failed", "detail": str(exc)}), 500, headers)

    # Dates/decimals/etc. from BigQuery aren't JSON-serialisable by default.
    rows = json.loads(json.dumps(rows, default=str))

    return (
        jsonify({"patient_id": patient_id, "count": len(rows), "results": rows}),
        200,
        headers,
    )

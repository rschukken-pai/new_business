"""
Cloud Function: get_new_business

Returns new-business records for a given patient from
`pai-production-395410.PAP.new_business`.

Deploy (Cloud Functions, 2nd gen, Python 3.12):

  gcloud functions deploy get-new-business \
    --gen2 \
    --runtime=python312 \
    --region=asia-southeast2 \
    --source=. \
    --entry-point=get_new_business \
    --trigger-http \
    --no-allow-unauthenticated \
    --project=pai-production-395410

The function's runtime service account needs, at minimum:
  - roles/bigquery.dataViewer  on the PAP dataset (reads new_business and
    the views/tables it's built from)
  - roles/bigquery.jobUser     on the project (runs query jobs)

Call it with either:
  GET  https://<function-url>?patient_id=2041125588483179604
  POST https://<function-url>   body: {"patient_id": "2041125588483179604"}

`--no-allow-unauthenticated` is intentional: this endpoint returns
patient-linked contact/business data, so callers should present a GCP
identity token (`gcloud auth print-identity-token`) or another auth layer
in front of it, rather than leaving it public.
"""

import json

import functions_framework
from flask import jsonify
from google.cloud import bigquery

PROJECT_ID = "pai-production-395410"
DATASET = "PAP"
TABLE = "new_business"

# `patient` in PAP.new_business holds Cliniko patient IDs, which are large
# integers (e.g. 2041125588483179604) -- bind as INT64, not STRING.
QUERY = f"""
SELECT *
FROM `{PROJECT_ID}.{DATASET}.{TABLE}` AS NB
WHERE NB.patient = @patient_id
"""

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
    """HTTP Cloud Function.

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
    elif request.method == "POST":
        body = request.get_json(silent=True) or {}
        raw_patient_id = body.get("patient_id") or request.args.get("patient_id")
    else:
        return (jsonify({"error": "Method not allowed"}), 405, headers)

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
        query_job = _get_client().query(QUERY, job_config=job_config)
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

# get-new-business API

A small HTTP API with one argument, `patient_id`, that runs:

```sql
SELECT *
FROM `pai-production-395410.PAP.new_business` AS NB
WHERE NB.patient = @patient_id
```

against BigQuery and returns the rows as JSON. Built as a Google Cloud
Function (2nd gen, Python) since it lives right next to the `PAP` dataset
it queries.

`patient_id` is bound as an `INT64` query parameter (not string-concatenated
into the SQL), both to avoid SQL injection and because Cliniko patient IDs
in this dataset are large integers, e.g. `2041125588483179604`.

## Files

- `main.py` — the function (`get_new_business`)
- `requirements.txt` — dependencies

## Deploy

```bash
gcloud functions deploy get-new-business \
  --gen2 \
  --runtime=python312 \
  --region=asia-southeast2 \
  --source=. \
  --entry-point=get_new_business \
  --trigger-http \
  --no-allow-unauthenticated \
  --project=pai-production-395410
```

Pick whichever `--region` your other PAP infrastructure runs in.

### Permissions

Grant the function's runtime service account (by default
`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`, or specify
`--service-account` for a dedicated one):

- `roles/bigquery.dataViewer` on the `PAP` dataset
- `roles/bigquery.jobUser` on the `pai-production-395410` project

```bash
bq add-iam-policy-binding \
  --member="serviceAccount:YOUR_SA@pai-production-395410.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" \
  pai-production-395410:PAP

gcloud projects add-iam-policy-binding pai-production-395410 \
  --member="serviceAccount:YOUR_SA@pai-production-395410.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

## Why authenticated by default

`new_business` returns patient-linked business/contact details, so the
deploy command above uses `--no-allow-unauthenticated`. Callers authenticate
with a GCP identity token:

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://REGION-pai-production-395410.cloudfunctions.net/get-new-business?patient_id=2041125588483179604"
```

If you'd rather front it with your own API key / auth layer (e.g. an
API Gateway, or a shared secret checked inside `main.py`), that works too —
just don't flip it to `--allow-unauthenticated` without adding some other
form of access control in front of it.

## Calling it

GET:

```bash
curl "https://<function-url>?patient_id=2041125588483179604"
```

POST:

```bash
curl -X POST "https://<function-url>" \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "2041125588483179604"}'
```

Response shape:

```json
{
  "patient_id": 2041125588483179604,
  "count": 1,
  "results": [
    {
      "business_name": "...",
      "address_1": "...",
      "...": "..."
    }
  ]
}
```

Missing/non-numeric `patient_id` returns `400`; a query failure returns
`500` with the BigQuery error message in `detail`.

## Running locally

```bash
pip install -r requirements.txt
gcloud auth application-default login   # local credentials for the BigQuery client
functions-framework --target=get_new_business --debug
# in another terminal:
curl "http://localhost:8080?patient_id=2041125588483179604"
```

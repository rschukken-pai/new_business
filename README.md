# get-new-business API

A small HTTP API with one argument, `patient_id`, that runs:

```sql
SELECT *
FROM `<PROJECT_ID>.<DATASET>.<TABLE>` AS NB
WHERE NB.patient = @patient_id
```

against BigQuery and returns the rows as JSON. Deployed as a **Cloud Run
function** — the current evolution of Cloud Functions 2nd gen, which shows
up under "Cloud Run functions" in the console/Run product, built from
source via buildpacks (no Dockerfile needed).

`patient_id` is bound as an `INT64` query parameter (not string-concatenated
into the SQL), both to avoid SQL injection and because the patient IDs in
this table are large integers.

## Files

- `main.py` — the function (`get_new_business`)
- `requirements.txt` — dependencies
- `credentials.py` — **not included here** (gitignored). Your actual
  project ID, dataset, table, and API key live only in this file (locally)
  or as Cloud Run env vars/secrets (in production). Nothing else in this
  repo — not `main.py`, not this README, not any command below — contains
  those values; copy `credentials.py.example` to create it. See
  "Config: credentials.py vs. environment variables" below.

## Auth model

This service returns patient-linked contact/business data, so it needs
*some* auth. Two options:

- **Calling it yourself / from another GCP service** (gcloud, a script with
  ADC, another Cloud Run service): use GCP IAM auth (`--no-allow-unauthenticated`,
  callers send a Google identity token).
- **Calling it from a third-party SaaS tool that can't mint GCP tokens**
  (Pabbly Connect, Zapier, Make, a plain webhook): IAM auth won't work
  there. Instead this deploys `--allow-unauthenticated` at the Cloud Run
  layer, but `main.py` itself checks every request for a shared secret
  (`API_KEY`) sent as an `X-API-Key` header (or `api_key` query/body param)
  and returns `401` if it's missing or wrong. **This is what's currently
  wired up**, since you're calling it from Pabbly.

If you later decide nothing outside GCP needs to call this, switch back to
`--no-allow-unauthenticated` and you can drop the API-key check.

## Config: credentials.py vs. environment variables

`main.py` resolves `PROJECT_ID`, `DATASET`, `TABLE`, and `API_KEY` the same
way, in this order:

1. An environment variable, if set — this is what Cloud Run uses in
   production, via `--set-env-vars` / `--set-secrets` on deploy.
2. Otherwise, `credentials.py`, if present — local dev only.

There's no third fallback and no hardcoded default: if a value is missing
both ways, the function returns `500` naming which config keys are unset,
rather than silently running against a default. `credentials.py` is never
in the deployed container (excluded via `.gcloudignore`) and never in git
(excluded via `.gitignore`), so those four values only ever exist in one
of two places: your local `credentials.py`, or Secret Manager / Cloud
Run's own env var config.

Set it up locally:

```bash
cp credentials.py.example credentials.py
```

then edit `credentials.py` and fill in the four real values — your GCP
project ID, the BigQuery dataset and table, and an API key matching what
you'll store in Secret Manager (see step 1 of Deploy, below).

The commands in the rest of this README load those same values from
`credentials.py` into shell variables rather than spelling them out, so
copy-pasting a command here never leaks them either:

```bash
eval "$(python3 -c '
import credentials as c
print(f"PROJECT_ID={c.PROJECT_ID}")
print(f"DATASET={c.DATASET}")
print(f"TABLE={c.TABLE}")
')"
```

Run that once per shell session before the commands below (they assume
`$PROJECT_ID`, `$DATASET`, `$TABLE` are set).

## Deploy

1. Pick a secret value for `API_KEY` (matching what you put in
   `credentials.py`) and store it in Secret Manager:

   ```bash
   printf '%s' 'REPLACE_WITH_A_LONG_RANDOM_SECRET' | \
     gcloud secrets create get-new-business-api-key \
       --data-file=- \
       --project="$PROJECT_ID"
   ```

   (Generate a random one with e.g. `openssl rand -hex 32` — use the same
   value in `credentials.py` so local testing matches production.)

2. Deploy:

   ```bash
   gcloud run deploy get-new-business \
     --source=. \
     --function=get_new_business \
     --region=asia-southeast2 \
     --allow-unauthenticated \
     --set-env-vars="PROJECT_ID=$PROJECT_ID,DATASET=$DATASET,TABLE=$TABLE" \
     --set-secrets=API_KEY=get-new-business-api-key:latest \
     --project="$PROJECT_ID"
   ```

   Pick whichever `--region` your other infrastructure runs in.

   (`gcloud functions deploy get-new-business --gen2 --runtime=python312 --entry-point=get_new_business --trigger-http ...` still works too and deploys the same underlying Cloud Run function.)

3. The Cloud Run service's own runtime service account also needs read access to Secret Manager — `gcloud run deploy --set-secrets` grants this automatically for the deploying user's default service account, but double check if you're using a custom one.

### BigQuery permissions

Grant the function's runtime service account (by default
`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`, or specify
`--service-account` for a dedicated one):

- `roles/bigquery.dataViewer` on the dataset
- `roles/bigquery.jobUser` on the project

```bash
bq add-iam-policy-binding \
  --member="serviceAccount:YOUR_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" \
  "$PROJECT_ID:$DATASET"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:YOUR_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

## Calling it from Pabbly Connect

1. In your Pabbly Connect workflow, add an action step using the built-in
   **"HTTP Request"** app (sometimes listed as a generic webhook/API-call
   action, not a named service integration).
2. Configure it:
   - **Method**: `GET` (simplest) or `POST`
   - **URL**: the Cloud Run URL from the deploy output, e.g.
     `https://get-new-business-xxxxx-as.a.run.app`
   - **Headers**: add `X-API-Key` = the same secret you stored in
     `get-new-business-api-key`
   - **Params / Body**: map `patient_id` to whatever field from an earlier
     step in your workflow holds the patient's ID (e.g. from a Cliniko or
     form-submission trigger)
3. Pabbly will show you the raw JSON response
   (`{"patient_id": ..., "count": ..., "results": [...]}`) that you can then
   map into later steps of the workflow.

Store the API key as a Pabbly custom/static variable (if your plan
supports it) rather than pasting it into every workflow, so it's easy to
rotate later.

## Calling it manually / for testing

GET:

```bash
curl "https://<run-url>?patient_id=<id>" \
  -H "X-API-Key: <your secret>"
```

POST:

```bash
curl -X POST "https://<run-url>" \
  -H "X-API-Key: <your secret>" \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "<id>"}'
```

Response shape:

```json
{
  "patient_id": 123456789,
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

- Missing/wrong `X-API-Key` → `401`
- Missing/non-numeric `patient_id` → `400`
- BigQuery query failure → `500` with the error in `detail`
- `PROJECT_ID`/`DATASET`/`TABLE`/`API_KEY` not fully configured on the
  service → `500` naming which keys are missing (fails closed rather than
  silently running with a default or allowing unauthenticated access)

## Running locally

```bash
pip install -r requirements.txt
gcloud auth application-default login   # local credentials for the BigQuery client
cp credentials.py.example credentials.py   # then edit it, see "Config" above
functions-framework --target=get_new_business --debug
# in another terminal:
curl "http://localhost:8080?patient_id=<id>&api_key=<value from credentials.py>"
```

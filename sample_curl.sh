curl -X POST https://asia-southeast2-pai-production-395410.cloudfunctions.net/new_patient \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $(gcloud secrets versions access latest --secret='new_patient')" \
  -d '{"action": "new_patient", "patient_id": "60014768"}'
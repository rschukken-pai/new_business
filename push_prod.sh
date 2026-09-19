
gcloud functions deploy new_patient \
  --gen2 \
  --runtime=python312 \
  --region=asia-southeast2 \
  --source=. \
  --entry-point=hello_pubsub \
  --trigger-http \
  --allow-unauthenticated \
  --set-secrets="new_patient:latest"
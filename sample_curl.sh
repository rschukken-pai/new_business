
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

API_KEY=$(cd "$SCRIPT_DIR" && python3 -c "from credentials import API_KEY; print(API_KEY)")

curl -X POST https://asia-southeast2-pai-production-395410.cloudfunctions.net/new_business \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"action": "new_business", "patient_id": "60014768",business: 1811529042298406445}'
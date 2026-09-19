import credentials, paigoogle
import functions_framework
from flask import jsonify
from datetime import datetime, timezone
import os

from paigoogle import new_business

SHARED_SECRET = os.environ.get("SHARED_SECRET")


@functions_framework.http
def hello_pubsub(request):
    # Validate shared secret from Secret Manager (injected as env var)
    incoming_secret = request.headers.get("X-API-Key")
    if incoming_secret != SHARED_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    print("Hello_pubsub")
    currentTime = datetime.now(timezone.utc).replace(tzinfo=None)

    request_json = request.get_json(silent=True)

    if not request_json or "action" not in request_json:
        return jsonify({"error": "Missing 'action' in request body"}), 400

    action = request_json["action"]

    if action == "new_business":
        patient_id = request_json.get("patient_id")
        if not patient_id:
            return jsonify({"error": "Missing 'patient_id' in request body"}), 400

        business = request_json.get("business")
        if not business:
            return jsonify({"error": "Missing 'business' in request body"}), 400

        result = paigoogle.new_business(patient_id, business)
        return result

    else:
        print("Wrong input received")
        return jsonify({"error": "Wrong input received"}), 400


if __name__ == '__main__':
    print(new_business('2041125588483179604', '1811529042298406445'))
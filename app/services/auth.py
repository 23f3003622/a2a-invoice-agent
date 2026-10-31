
import hashlib
from flask import request, jsonify


def validate_request():
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer ") or not auth_header[7:].strip():
        return jsonify({"error": "Authentication required"}), 401

    if request.headers.get("A2A-Version") != "1.0":
        return jsonify({"error": "Unsupported A2A version"}), 400

    if request.method == "POST":
        content_type = request.headers.get("Content-Type", "").split(";")[0].strip()

        if content_type != "application/a2a+json":
            return jsonify({"error": "Unsupported media type"}), 415

    return None


def get_principal():
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip()
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

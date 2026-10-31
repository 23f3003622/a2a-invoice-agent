
import os
import hmac
from flask import request, jsonify


def validate_request():
    configured_tokens = os.getenv("A2A_BEARER_TOKENS", "")

    if not configured_tokens:
        configured_tokens = os.getenv("A2A_BEARER_TOKEN", "")

    valid_tokens = [
        token.strip()
        for token in configured_tokens.split(",")
        if token.strip()
    ]

    auth_header = request.headers.get("Authorization", "")
    supplied_token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    if not valid_tokens:
        return jsonify({"error": "Server configuration error"}), 500

    if not any(
        hmac.compare_digest(supplied_token, token)
        for token in valid_tokens
    ):
        return jsonify({"error": "Unauthorized"}), 401

    if request.headers.get("A2A-Version") != "1.0":
        return jsonify({"error": "Unsupported A2A version"}), 400

    if request.method == "POST":
        content_type = request.headers.get("Content-Type", "").split(";")[0].strip()

        if content_type != "application/a2a+json":
            return jsonify({"error": "Unsupported media type"}), 415

    return None


import hashlib
import json


def canonical_json(data):
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )


def get_message_hash(message):
    content = canonical_json(message)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_principal_hash(bearer_token):
    token = bearer_token.strip()
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

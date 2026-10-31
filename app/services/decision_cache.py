import json
import hashlib
from app.extensions import db
from app.models.decision_cache import DecisionCache
from sqlalchemy.exc import IntegrityError


CACHE_VERSION = "v1"


def canonical_json(data):
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )


def get_package_hash(package, policy_revision):
    content = {
        "cacheVersion": CACHE_VERSION,
        "policyRevision": policy_revision,
        "package": {
            key: value
            for key, value in package.items()
            if key != "packageId"
        }
    }

    return hashlib.sha256(
        canonical_json(content).encode("utf-8")
    ).hexdigest()


def get_cached_decision(package, policy_revision):
    package_hash = get_package_hash(package, policy_revision)

    cached = DecisionCache.query.filter_by(
        package_hash=package_hash
    ).first()

    if cached:
        return json.loads(cached.decision)

    return None


def save_decision(package, policy_revision, decision):
    package_hash = get_package_hash(package, policy_revision)

    existing = DecisionCache.query.filter_by(
        package_hash=package_hash
    ).first()

    if existing:
        return json.loads(existing.decision)

    record = DecisionCache(
        package_hash=package_hash,
        decision=canonical_json(decision)
    )

    db.session.add(record)

    try:
        db.session.commit()
        return decision

    except IntegrityError:
        db.session.rollback()

        existing = DecisionCache.query.filter_by(
            package_hash=package_hash
        ).first()

        if existing:
            return json.loads(existing.decision)

        raise
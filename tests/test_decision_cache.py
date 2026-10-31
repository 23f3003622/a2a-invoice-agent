import uuid

import pytest

from app import create_app
from app.extensions import db
from app.services.decision_cache import (
    get_cached_decision,
    save_decision,
    get_package_hash
)


@pytest.fixture
def app_context(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def test_equivalent_packages_reuse_cached_decision(app_context):
    package_one = {
        "packageId": "PKG-001",
        "documents": ["Invoice from Vendor A for INR 1000."]
    }

    package_two = {
        "packageId": "PKG-999",
        "documents": ["Invoice from Vendor A for INR 1000."]
    }

    policy_revision = "policy-v1"

    decision = {
        "action": "settle_invoice",
        "facts": {
            "vendorName": "Vendor A",
            "invoiceNumber": "INV-001",
            "amountMinor": 100000,
            "currency": "INR"
        },
        "evidenceRefs": ["[INV-1]", "[PAY-1]", "[REC-1]"],
        "rationale": "The invoice and payment records support settlement."
    }

    first_hash = get_package_hash(package_one, policy_revision)
    second_hash = get_package_hash(package_two, policy_revision)

    assert first_hash == second_hash

    save_decision(package_one, policy_revision, decision)

    cached = get_cached_decision(package_two, policy_revision)

    assert cached == decision

    assert get_cached_decision(
        package_two,
        "different-policy"
    ) is None
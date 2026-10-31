
import uuid
from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.drop_all()
        db.create_all()

        with app.test_client() as test_client:
            yield test_client

        db.session.remove()
        db.drop_all()


def make_package(number):
    package_id = f"PKG-{number:03d}"
    invoice_number = f"INV-{number:03d}"
    vendor = f"Vendor {number}"

    paragraph = (
        f"Invoice issued by {vendor}, number {invoice_number}, "
        f"for INR 1000. Payment and goods receipt are verified. "
        f"[INV-{number:03d}] [PAY-{number:03d}] [REC-{number:03d}]"
    )

    return {
        "packageId": package_id,
        "documents": [paragraph]
    }


def make_ai_response(batch_id, packages):
    proposals = []

    for package in packages:
        number = int(package["packageId"].split("-")[1])

        proposals.append({
            "packageId": package["packageId"],
            "actionId": str(uuid.uuid4()),
            "action": "settle_invoice",
            "facts": {
                "vendorName": f"Vendor {number}",
                "invoiceNumber": f"INV-{number:03d}",
                "amountMinor": 100000,
                "currency": "INR"
            },
            "evidenceRefs": [
                f"[INV-{number:03d}]",
                f"[PAY-{number:03d}]",
                f"[REC-{number:03d}]"
            ],
            "rationale": (
                f"Settlement is supported by [INV-{number:03d}] "
                f"and [PAY-{number:03d}]. Payment and goods receipt "
                "are verified in the supplied invoice evidence."
            )
        })

    return {
        "batchId": batch_id,
        "proposals": proposals
    }


def test_twelve_package_message_flow(client):
    batch_id = "TEST-BATCH-001"
    packages = [make_package(i) for i in range(1, 13)]

    message = {
        "messageId": "test-message-001",
        "parts": [{
            "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
            "data": {
                "batchId": batch_id,
                "policyRevision": "test-policy-v1",
                "packages": packages
            }
        }]
    }

    headers = {
        "Authorization": "Bearer integration-test-token",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json"
    }

    with patch(
        "app.routes.messages.analyze_batch",
        return_value=make_ai_response(batch_id, packages)
    ) as mock_ai:

        response = client.post(
            "/a2a/message:send",
            json={"message": message},
            headers=headers
        )

    assert response.status_code == 200

    body = response.get_json()
    task = body["task"]

    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert len(task["history"]) == 1
    assert len(task["artifacts"]) == 1

    artifact = task["artifacts"][0]
    assert len(artifact["parts"]) == 1

    part = artifact["parts"][0]
    assert part["mediaType"] == (
        "application/vnd.ga5.invoice-action-proposals+json"
    )

    proposals = part["data"]["proposals"]

    assert part["data"]["batchId"] == batch_id
    assert len(proposals) == 12
    assert len({p["packageId"] for p in proposals}) == 12
    assert len({p["actionId"] for p in proposals}) == 12

    mock_ai.assert_called_once()

    replay_response = client.post(
        "/a2a/message:send",
        json={"message": message},
        headers=headers
    )

    assert replay_response.status_code == 200
    replay_body = replay_response.get_json()
    assert replay_body["task"]["id"] == task["id"]
    mock_ai.assert_called_once()

    changed_message = {
        "messageId": "test-message-001",
        "parts": [{
            "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
            "data": {
                "batchId": "DIFFERENT-BATCH",
                "policyRevision": "test-policy-v1",
                "packages": packages
            }
        }]
    }

    conflict_response = client.post(
        "/a2a/message:send",
        json={"message": changed_message},
        headers=headers
    )

    assert conflict_response.status_code == 409
    mock_ai.assert_called_once()

def test_continuation_creates_receipts_for_accepted_actions(client):
    batch_id = "CONTINUATION-BATCH-001"
    packages = [make_package(i) for i in range(1, 13)]

    initial_message = {
        "messageId": "initial-continuation-test",
        "parts": [{
            "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
            "data": {
                "batchId": batch_id,
                "policyRevision": "test-policy-v1",
                "packages": packages
            }
        }]
    }

    headers = {
        "Authorization": "Bearer continuation-test-token",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json"
    }

    with patch(
        "app.routes.messages.analyze_batch",
        return_value=make_ai_response(batch_id, packages)
    ) as mock_ai:

        initial_response = client.post(
            "/a2a/message:send",
            json={"message": initial_message},
            headers=headers
        )

        assert initial_response.status_code == 200

        initial_task = initial_response.get_json()["task"]
        proposals = initial_task["artifacts"][0]["parts"][0]["data"]["proposals"]

        results = []

        for index, proposal in enumerate(proposals):
            results.append({
                "packageId": proposal["packageId"],
                "actionId": proposal["actionId"],
                "action": proposal["action"],
                "outcome": "ACCEPTED" if index < 6 else "REJECTED",
                "receiptNonce": f"nonce-{index + 1}-unique"
            })

        continuation_message = {
            "messageId": "continuation-message-001",
            "taskId": initial_task["id"],
            "contextId": initial_task["contextId"],
            "parts": [{
                "mediaType": "application/vnd.ga5.invoice-action-results+json",
                "data": {
                    "batchId": batch_id,
                    "results": results
                }
            }]
        }

        continuation_response = client.post(
            "/a2a/message:send",
            json={"message": continuation_message},
            headers=headers
        )

        assert continuation_response.status_code == 200

        completed_task = continuation_response.get_json()["task"]

        assert completed_task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert len(completed_task["history"]) == 2
        assert len(completed_task["artifacts"]) == 2

        receipt_part = completed_task["artifacts"][1]["parts"][0]

        assert receipt_part["mediaType"] == (
            "application/vnd.ga5.invoice-action-receipts+json"
        )

        receipt_data = receipt_part["data"]

        assert receipt_data["batchId"] == batch_id
        assert len(receipt_data["executions"]) == 6

        assert {
            item["packageId"] for item in receipt_data["executions"]
        } == {
            proposal["packageId"] for proposal in proposals[:6]
        }

        replay_response = client.post(
            "/a2a/message:send",
            json={"message": continuation_message},
            headers=headers
        )

        assert replay_response.status_code == 200
        assert replay_response.get_json()["task"]["id"] == initial_task["id"]
        mock_ai.assert_called_once()

def test_tampered_continuation_is_rejected(client):
    batch_id = "TAMPER-TEST-001"
    packages = [make_package(i) for i in range(1, 13)]

    initial_message = {
        "messageId": "tamper-initial-001",
        "parts": [{
            "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
            "data": {
                "batchId": batch_id,
                "policyRevision": "test-policy-v1",
                "packages": packages
            }
        }]
    }

    headers = {
        "Authorization": "Bearer tamper-test-token",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json"
    }

    with patch(
        "app.routes.messages.analyze_batch",
        return_value=make_ai_response(batch_id, packages)
    ) as mock_ai:

        initial_response = client.post(
            "/a2a/message:send",
            json={"message": initial_message},
            headers=headers
        )

        assert initial_response.status_code == 200

        task = initial_response.get_json()["task"]
        proposals = task["artifacts"][0]["parts"][0]["data"]["proposals"]

        results = []

        for proposal in proposals:
            results.append({
                "packageId": proposal["packageId"],
                "actionId": proposal["actionId"],
                "action": proposal["action"],
                "outcome": "ACCEPTED",
                "receiptNonce": "tamper-test-nonce"
            })

        results[0]["actionId"] = "incorrect-action-id"

        continuation_message = {
            "messageId": "tamper-continuation-001",
            "taskId": task["id"],
            "contextId": task["contextId"],
            "parts": [{
                "mediaType": "application/vnd.ga5.invoice-action-results+json",
                "data": {
                    "batchId": batch_id,
                    "results": results
                }
            }]
        }

        response = client.post(
            "/a2a/message:send",
            json={"message": continuation_message},
            headers=headers
        )

        assert response.status_code == 409

        task_response = client.get(
            f"/a2a/tasks/{task['id']}",
            headers=headers
        )

        assert task_response.status_code == 200

        unchanged_task = task_response.get_json()

        assert unchanged_task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert len(unchanged_task["artifacts"]) == 1
        mock_ai.assert_called_once()
def test_api_reuses_cached_decisions_with_fresh_action_ids(client):
    first_batch_id = "CACHE-BATCH-001"
    second_batch_id = "CACHE-BATCH-002"

    first_packages = [make_package(i) for i in range(1, 13)]

    second_packages = [
        {
            **package,
            "packageId": f"OTHER-{i:03d}"
        }
        for i, package in enumerate(first_packages, start=1)
    ]

    headers = {
        "Authorization": "Bearer cache-integration-token",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json"
    }

    def make_message(message_id, batch_id, packages):
        return {
            "messageId": message_id,
            "parts": [{
                "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
                "data": {
                    "batchId": batch_id,
                    "policyRevision": "test-policy-v1",
                    "packages": packages
                }
            }]
        }

    with patch(
        "app.routes.messages.analyze_batch",
        side_effect=lambda batch_id, policy_revision, packages:
            make_ai_response(batch_id, packages)
    ) as mock_ai:

        first_response = client.post(
            "/a2a/message:send",
            json={
                "message": make_message(
                    "cache-message-001",
                    first_batch_id,
                    first_packages
                )
            },
            headers=headers
        )

        assert first_response.status_code == 200

        first_task = first_response.get_json()["task"]
        first_proposals = (
            first_task["artifacts"][0]["parts"][0]["data"]["proposals"]
        )

        second_response = client.post(
            "/a2a/message:send",
            json={
                "message": make_message(
                    "cache-message-002",
                    second_batch_id,
                    second_packages
                )
            },
            headers=headers
        )

        assert second_response.status_code == 200

        second_task = second_response.get_json()["task"]
        second_proposals = (
            second_task["artifacts"][0]["parts"][0]["data"]["proposals"]
        )

        assert len(first_proposals) == 12
        assert len(second_proposals) == 12

        assert mock_ai.call_count == 1

        for first, second in zip(first_proposals, second_proposals):
            assert first["action"] == second["action"]
            assert first["facts"] == second["facts"]
            assert first["evidenceRefs"] == second["evidenceRefs"]
            assert first["actionId"] != second["actionId"]
            assert first["packageId"] != second["packageId"]
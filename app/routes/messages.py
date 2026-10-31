import json
import uuid

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.task import Task
from app.models.message_record import MessageRecord
from app.services.continuation import process_continuation
from app.services.idempotency import get_message_hash
from app.services.auth import get_principal
from app.services.ai_engine import analyze_batch
from app.services.validator import validate_batch, validate_proposal
from app.services.decision_cache import get_cached_decision, save_decision

messages_bp = Blueprint("messages", __name__)


def a2a_response(data, status_code=200):
    response = jsonify(data)
    response.status_code = status_code
    response.content_type = "application/a2a+json"
    return response


def serialize_task(task):
    return {
        "kind": "task",
        "id": task.task_id,
        "contextId": task.context_id,
        "status": {"state": task.state},
        "history": json.loads(task.history),
        "artifacts": json.loads(task.artifacts)
    }


def get_message_parts(message):
    parts = message.get("parts", [])

    if not isinstance(parts, list):
        return None

    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("mediaType") ==
            "application/vnd.ga5.invoice-claim-batch+json"
        ):
            return part.get("data")

    return None


def get_continuation_data(message):
    parts = message.get("parts", [])

    if not isinstance(parts, list):
        return None

    for part in parts:
        if not isinstance(part, dict):
            continue

        if (
            part.get("mediaType") ==
            "application/vnd.ga5.invoice-action-results+json"
        ):
            return part.get("data")

    return None



def handle_continuation(message, principal):
    task_id = message.get("taskId")
    context_id = message.get("contextId")
    message_id = message.get("messageId") or message.get("id")

    if not all(
        isinstance(value, str) and value
        for value in [task_id, context_id, message_id]
    ):
        return a2a_response({"error": "Invalid continuation message"}, 400)

    message_hash = get_message_hash(message)

    existing = MessageRecord.query.filter_by(
        principal=principal,
        message_id=message_id
    ).first()

    if existing:
        if existing.message_hash != message_hash:
            return a2a_response(
                {"error": "IDEMPOTENCY_CONFLICT"}, 409
            )

        task = Task.query.filter_by(
            task_id=existing.task_id,
            owner=principal
        ).first()

        if task is None:
            return a2a_response({"error": "Task not found"}, 404)

        return a2a_response({"task": serialize_task(task)})

    task = Task.query.filter_by(
        task_id=task_id,
        context_id=context_id,
        owner=principal
    ).first()

    if task is None:
        return a2a_response({"error": "Task not found"}, 404)

    continuation_data = get_continuation_data(message)

    if continuation_data is None:
        return a2a_response(
            {"error": "Continuation data is missing"}, 400
        )

    record = MessageRecord(
        principal=principal,
        message_id=message_id,
        message_hash=message_hash,
        task_id=task_id
    )

    try:
        db.session.add(record)

        process_continuation(
            task,
            message,
            continuation_data
        )

        db.session.commit()
        db.session.refresh(task)

    except IntegrityError:
        db.session.rollback()

        existing = MessageRecord.query.filter_by(
            principal=principal,
            message_id=message_id
        ).first()

        if existing and existing.message_hash == message_hash:
            task = Task.query.filter_by(
                task_id=existing.task_id,
                owner=principal
            ).first()

            if task:
                return a2a_response({"task": serialize_task(task)})

        return a2a_response(
            {"error": "IDEMPOTENCY_CONFLICT"}, 409
        )

    except ValueError as error:
        db.session.rollback()
        return a2a_response({"error": str(error)}, 409)

    return a2a_response({"task": serialize_task(task)})



@messages_bp.route("/a2a/message:send", methods=["POST"])
def send_message():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return a2a_response({"error": "Invalid request body"}, 400)

    message = body.get("message")

    if not isinstance(message, dict):
        return a2a_response({"error": "Message is required"}, 400)

    message_id = message.get("messageId") or message.get("id")

    principal = get_principal()

    if message.get("taskId"):
        return handle_continuation(message, principal)

    if not isinstance(message_id, str) or not message_id:
        return a2a_response({"error": "Message ID is required"}, 400)

    batch = get_message_parts(message)

    if not isinstance(batch, dict):
        return a2a_response({"error": "Invoice batch is missing"}, 400)

    batch_id = batch.get("batchId")
    policy_revision = batch.get("policyRevision")
    packages = batch.get("packages")

    if isinstance(packages, list):
        current_app.logger.info(
            "Invoice batch size: %s packages, %s total characters",
            len(packages),
            sum(len(json.dumps(p, ensure_ascii=False)) for p in packages)
        )
        for package in packages:
            current_app.logger.info(
                "Package %s: %s characters",
                package.get("packageId", "unknown"),
                len(json.dumps(package, ensure_ascii=False))
            )

    if (
        not isinstance(batch_id, str)
        or not batch_id
        or not isinstance(policy_revision, str)
        or not policy_revision
        or not isinstance(packages, list)
        or len(packages) != 12
    ):
        return a2a_response({"error": "Invalid invoice batch"}, 400)

    if any(not isinstance(package, dict) for package in packages):
        return a2a_response({"error": "Invalid invoice package"}, 400)

    package_ids = [package.get("packageId") for package in packages]

    if (
        any(not isinstance(package_id, str) or not package_id for package_id in package_ids)
        or len(set(package_ids)) != len(package_ids)
    ):
        return a2a_response({"error": "Invalid or duplicate package IDs"}, 400)

    message_hash = get_message_hash(message)

    existing = MessageRecord.query.filter_by(
        principal=principal,
        message_id=message_id
    ).first()

    if existing:
        if existing.message_hash != message_hash:
            return a2a_response(
                {"error": "IDEMPOTENCY_CONFLICT"}, 409
            )

        task = Task.query.filter_by(
            task_id=existing.task_id,
            owner=principal
        ).first()

        if task is None:
            return a2a_response({"error": "Task not found"}, 404)

        return a2a_response({"task": serialize_task(task)})

    task_id = str(uuid.uuid4())
    context_id = message.get("contextId") or str(uuid.uuid4())

    task = Task(
        task_id=task_id,
        context_id=context_id,
        owner=principal,
        batch_id=batch_id,
        state="TASK_STATE_SUBMITTED",
        history=json.dumps([message]),
        artifacts=json.dumps([])
    )

    record = MessageRecord(
        principal=principal,
        message_id=message_id,
        message_hash=message_hash,
        task_id=task_id
    )

    try:
        db.session.add(task)
        db.session.add(record)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        existing = MessageRecord.query.filter_by(
            principal=principal,
            message_id=message_id
        ).first()

        if existing and existing.message_hash == message_hash:
            task = Task.query.filter_by(
                task_id=existing.task_id,
                owner=principal
            ).first()

            if task:
                return a2a_response({"task": serialize_task(task)})

        return a2a_response(
            {"error": "IDEMPOTENCY_CONFLICT"}, 409
        )

    try:
        package_map = {
            package["packageId"]: package
            for package in packages
        }

        proposals_by_id = {}
        uncached_packages = []

        for package in packages:
            cached = get_cached_decision(package, policy_revision)

            if cached is None:
                uncached_packages.append(package)

            else:
                cached["packageId"] = package["packageId"]
                cached["actionId"] = str(uuid.uuid4())

                validated = validate_proposal(cached, package)
                proposals_by_id[package["packageId"]] = validated

        if uncached_packages:
            ai_result = analyze_batch(
                batch_id,
                policy_revision,
                uncached_packages
            )

            new_proposals = validate_batch(
                ai_result,
                uncached_packages,
                batch_id
            )

            for proposal in new_proposals["proposals"]:
                package = package_map[proposal["packageId"]]

                decision = proposal.copy()
                decision.pop("packageId", None)
                decision.pop("actionId", None)

                saved_decision = save_decision(
                    package,
                    policy_revision,
                    decision
                )

                saved_decision["packageId"] = package["packageId"]
                saved_decision["actionId"] = str(uuid.uuid4())

                validated = validate_proposal(
                    saved_decision,
                    package
                )

                proposals_by_id[package["packageId"]] = validated

        combined_proposals = [
            proposals_by_id[package["packageId"]]
            for package in packages
        ]

        validated = validate_batch(
            {
                "batchId": batch_id,
                "proposals": combined_proposals
            },
            packages,
            batch_id
        )

        artifact = {
            "parts": [{
                "mediaType": "application/vnd.ga5.invoice-action-proposals+json",
                "data": validated
            }]
        }

        result = db.session.execute(
            update(Task)
            .where(
                Task.task_id == task_id,
                Task.owner == principal,
                Task.state == "TASK_STATE_SUBMITTED"
            )
            .values(
                state="TASK_STATE_INPUT_REQUIRED",
                artifacts=json.dumps([artifact])
            )
        )

        if result.rowcount != 1:
            db.session.rollback()
            return a2a_response(
                {"error": "Task was canceled or already changed"},
                409
            )

        db.session.commit()
        db.session.refresh(task)

    except Exception:
        current_app.logger.exception(
            "Invoice analysis failed for task %s", task_id
        )

        db.session.rollback()

        task = Task.query.filter_by(
            task_id=task_id,
            owner=principal
        ).first()

        if task and task.state == "TASK_STATE_SUBMITTED":
            task.state = "TASK_STATE_FAILED"
            db.session.commit()

        return a2a_response(
            {"error": "Invoice analysis could not be completed"},
            500
        )

    return a2a_response({"task": serialize_task(task)})

import json
from sqlalchemy import update

from app.extensions import db
from app.models.task import Task
from app.services.receipt_validator import validate_continuation


def process_continuation(task, message, data):
    if task.state != "TASK_STATE_INPUT_REQUIRED":
        raise ValueError("Task is not awaiting input")

    artifacts = json.loads(task.artifacts)

    proposal_count = 0
    receipt_count = 0

    for artifact in artifacts:
        for part in artifact.get("parts", []):
            media_type = part.get("mediaType")

            if media_type == "application/vnd.ga5.invoice-action-proposals+json":
                proposal_count += 1

            if media_type == "application/vnd.ga5.invoice-action-receipts+json":
                receipt_count += 1

    if proposal_count != 1 or receipt_count != 0:
        raise ValueError("Invalid task artifacts")

    result = validate_continuation(task, message, data)

    history = json.loads(task.history)
    history.append(message)

    receipt_artifact = {
        "parts": [{
            "mediaType": "application/vnd.ga5.invoice-action-receipts+json",
            "data": result
        }]
    }

    artifacts.append(receipt_artifact)

    update_result = db.session.execute(
        update(Task)
        .where(
            Task.task_id == task.task_id,
            Task.owner == task.owner,
            Task.state == "TASK_STATE_INPUT_REQUIRED"
        )
        .values(
            state="TASK_STATE_COMPLETED",
            history=json.dumps(history),
            artifacts=json.dumps(artifacts)
        )
        .execution_options(synchronize_session=False)
    )

    if update_result.rowcount != 1:
        db.session.rollback()
        raise ValueError("Task was already completed or changed")

    db.session.commit()

    return result

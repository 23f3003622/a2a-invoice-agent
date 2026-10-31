from app.services.auth import get_principal
from flask import Blueprint, jsonify, request
from app.models.task import Task
from app.extensions import db

import json

tasks_bp = Blueprint("tasks", __name__)



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
        "status": {
            "state": task.state
        },
        "history": json.loads(task.history),
        "artifacts": json.loads(task.artifacts)
    }



@tasks_bp.route("/a2a/tasks", methods=["GET"])
def list_tasks():
    principal = get_principal()

    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(100, max(1, int(request.args.get("pageSize", 20))))
    except ValueError:
        return a2a_response({"error": "Invalid pagination parameters"}, 400)

    pagination = Task.query.filter_by(
        owner=principal
    ).order_by(
        Task.created_at.desc()
    ).paginate(
        page=page,
        per_page=page_size,
        error_out=False
    )

    return a2a_response({
    "tasks": [serialize_task(t) for t in pagination.items]
})



@tasks_bp.route("/a2a/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    principal = get_principal()

    task = Task.query.filter_by(
        task_id=task_id,
        owner=principal
    ).first()

    if task is None:
        return a2a_response({"error": "Task not found"}, 404)

    return a2a_response(serialize_task(task))


@tasks_bp.route("/a2a/tasks/<task_id>:cancel", methods=["POST"])
def cancel_task(task_id):
    principal = get_principal()

    terminal_states = [
        "TASK_STATE_COMPLETED",
        "TASK_STATE_CANCELED",
        "TASK_STATE_FAILED",
        "TASK_STATE_REJECTED"
    ]

    result = db.session.execute(
        db.update(Task)
        .where(
            Task.task_id == task_id,
            Task.owner == principal,
            Task.state.notin_(terminal_states)
        )
        .values(state="TASK_STATE_CANCELED")
    )

    if result.rowcount == 0:
        db.session.rollback()

        task = Task.query.filter_by(
            task_id=task_id,
            owner=principal
        ).first()

        if task is None:
            return a2a_response({"error": "Task not found"}, 404)

        return a2a_response({
            "error": "Task is already in a terminal state"
        }, 409)

    db.session.commit()

    task = Task.query.filter_by(
        task_id=task_id,
        owner=principal
    ).first()

    return a2a_response(serialize_task(task), 200)
import hashlib

import pytest

from app import create_app
from app.extensions import db
from app.models.task import Task


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


def make_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "A2A-Version": "1.0"
    }


def test_task_owner_isolation(client):
    token_a = "user-a-test-token"
    token_b = "user-b-test-token"

    owner = hashlib.sha256(token_a.encode()).hexdigest()

    task = Task(
        task_id="ownership-test-task-001",
        context_id="ownership-test-context",
        owner=owner,
        batch_id="ownership-test-batch",
        state="TASK_STATE_INPUT_REQUIRED"
    )

    db.session.add(task)
    db.session.commit()

    response_a = client.get(
        "/a2a/tasks",
        headers=make_headers(token_a)
    )

    response_b = client.get(
        "/a2a/tasks",
        headers=make_headers(token_b)
    )

    assert response_a.status_code == 200
    assert len(response_a.get_json()["tasks"]) == 1

    assert response_b.status_code == 200
    assert len(response_b.get_json()["tasks"]) == 0

    own_task = client.get(
        "/a2a/tasks/ownership-test-task-001",
        headers=make_headers(token_a)
    )

    чужой_task = client.get(
        "/a2a/tasks/ownership-test-task-001",
        headers=make_headers(token_b)
    )

    assert own_task.status_code == 200
    assert чужой_task.status_code == 404
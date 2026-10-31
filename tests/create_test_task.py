
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import hashlib
import uuid

from app import create_app
from app.extensions import db
from app.models.task import Task

app = create_app()

token = "dev-secret-token-change-later"
owner = hashlib.sha256(token.encode()).hexdigest()

with app.app_context():
    task_id = str(uuid.uuid4())

    task = Task(
        task_id=task_id,
        context_id=str(uuid.uuid4()),
        owner=owner,
        batch_id="TEST-BATCH-001",
        state="TASK_STATE_INPUT_REQUIRED",
        history="[]",
        artifacts="[]"
    )

    db.session.add(task)
    db.session.commit()

    print("Test task created:", task_id)

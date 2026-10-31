from app.extensions import db
from datetime import datetime
import uuid


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)

    task_id = db.Column(
        db.String(100),
        unique=True,
        nullable=False,
        default=lambda: str(uuid.uuid4())
    )

    context_id = db.Column(
        db.String(100),
        nullable=False
    )

    owner = db.Column(
        db.String(255),
        nullable=False,
        index=True
    )

    batch_id = db.Column(
        db.String(255),
        nullable=False
    )

    state = db.Column(
        db.String(50),
        nullable=False,
        default="TASK_STATE_SUBMITTED"
    )

    history = db.Column(
        db.Text,
        nullable=False,
        default="[]"
    )

    artifacts = db.Column(
        db.Text,
        nullable=False,
        default="[]"
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
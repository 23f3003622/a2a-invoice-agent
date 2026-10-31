from app.extensions import db
from datetime import datetime


class MessageRecord(db.Model):
    __tablename__ = "message_records"

    id = db.Column(db.Integer, primary_key=True)

    principal = db.Column(
        db.String(255),
        nullable=False
    )

    message_id = db.Column(
        db.String(255),
        nullable=False
    )

    message_hash = db.Column(
        db.String(64),
        nullable=False
    )

    task_id = db.Column(
        db.String(100),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "principal",
            "message_id",
            name="unique_principal_message"
        ),
    )
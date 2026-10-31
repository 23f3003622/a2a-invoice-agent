from app.extensions import db
from datetime import datetime


class DecisionCache(db.Model):
    __tablename__ = "decision_cache"

    id = db.Column(db.Integer, primary_key=True)

    package_hash = db.Column(
        db.String(64),
        unique=True,
        nullable=False
    )

    decision = db.Column(
        db.Text,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
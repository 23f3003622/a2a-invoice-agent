
from app.extensions import db
from app.models.message_record import MessageRecord
from app.services.idempotency import get_message_hash


def find_existing_message(principal, message_id):
    return MessageRecord.query.filter_by(
        principal=principal,
        message_id=message_id
    ).first()


def save_message_record(principal, message_id, message, task_id):
    record = MessageRecord(
        principal=principal,
        message_id=message_id,
        message_hash=get_message_hash(message),
        task_id=task_id
    )

    db.session.add(record)
    db.session.commit()

    return record

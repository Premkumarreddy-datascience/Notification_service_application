from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from api.app import models, schemas
from api.app.database import SessionLocal, engine
import pika
import json
import os

models.Base.metadata.create_all(bind=engine)

app = FastAPI()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_rabbitmq_channel():
    rabbitmq_url = os.getenv("RABBITMQ_URL")
    connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue='notifications')
    return channel


@app.post("/notifications/", response_model=schemas.Notification)
def create_notification(notification: schemas.NotificationCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.id == notification.user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get user preferences if types not specified
    if not notification.types:
        preferences = db.query(models.NotificationPreference).filter(
            models.NotificationPreference.user_id == notification.user_id
        ).first()
        if preferences:
            notification.types = []
            if preferences.email_enabled:
                notification.types.append("email")
            if preferences.sms_enabled:
                notification.types.append("sms")
            if preferences.in_app_enabled:
                notification.types.append("in_app")
        else:
            notification.types = ["email", "in_app"]  # Default

    # Create DB record
    db_notification = models.Notification(
        user_id=notification.user_id,
        title=notification.title,
        message=notification.message,
        notification_type=",".join(notification.types)
    )
    db.add(db_notification)
    db.commit()
    db.refresh(db_notification)

    # Send to queue
    channel = get_rabbitmq_channel()
    channel.basic_publish(
        exchange='',
        routing_key='notifications',
        body=json.dumps({
            "notification_id": db_notification.id,
            "user_id": notification.user_id,
            "title": notification.title,
            "message": notification.message,
            "types": notification.types
        })
    )

    return db_notification


@app.get("/users/{user_id}/notifications/", response_model=list[schemas.Notification])
def read_user_notifications(user_id: int, db: Session = Depends(get_db)):
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id
    ).order_by(models.Notification.created_at.desc()).all()
    return notifications
import pika
import json
import smtplib
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import time

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    title = Column(String(255))
    message = Column(Text)
    notification_type = Column(String(20))
    status = Column(String(20), default="pending")
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime)


# Email config
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


def send_email(email, subject, message):
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            email_message = f"Subject: {subject}\n\n{message}"
            server.sendmail(SMTP_USER, email, email_message)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_sms(phone, message):
    # In a real implementation, integrate with SMS provider like Twilio
    print(f"[SMS] To {phone}: {message}")
    return True


def update_notification_status(db, notification_id, status, retry_count=0):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification:
        notification.status = status
        notification.retry_count = retry_count
        if status == "sent":
            notification.sent_at = datetime.utcnow()
        db.commit()


def process_notification(ch, method, properties, body):
    db = SessionLocal()
    try:
        data = json.loads(body)
        print(f"Processing notification {data['notification_id']}")

        # Get user from DB (in a real app, you'd have a User model)
        # For demo, we'll just use the data from the message

        # Process each notification type
        for notification_type in data["types"]:
            max_retries = 3
            retry_count = 0
            success = False

            while not success and retry_count < max_retries:
                try:
                    if notification_type == "email":
                        success = send_email(
                            email="user@example.com",  # In real app, get from user record
                            subject=data["title"],
                            message=data["message"]
                        )
                    elif notification_type == "sms":
                        success = send_sms(
                            phone="+1234567890",  # In real app, get from user record
                            message=data["message"]
                        )
                    elif notification_type == "in_app":
                        # For in-app, we just mark as sent
                        success = True

                    if success:
                        print(f"Notification {data['notification_id']} sent via {notification_type}")
                    else:
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"Retry {retry_count} for notification {data['notification_id']}")
                            time.sleep(2 ** retry_count)  # Exponential backoff
                except Exception as e:
                    print(f"Error processing notification {data['notification_id']}: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(2 ** retry_count)

            # Update status in DB
            if success:
                update_notification_status(db, data["notification_id"], "sent")
            else:
                update_notification_status(db, data["notification_id"], "failed", retry_count)

    except Exception as e:
        print(f"Error processing message: {e}")
    finally:
        db.close()


def main():
    rabbitmq_url = os.getenv("RABBITMQ_URL")
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            channel = connection.channel()
            channel.queue_declare(queue='notifications')

            print("Worker started. Waiting for messages...")

            channel.basic_consume(
                queue='notifications',
                on_message_callback=process_notification,
                auto_ack=True
            )

            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            print("Connection failed. Retrying in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            print("Worker stopped")
            break
        except Exception as e:
            print(f"Unexpected error: {e}. Restarting in 10 seconds...")
            time.sleep(10)


if __name__ == "__main__":
    main()
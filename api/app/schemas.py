from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class NotificationBase(BaseModel):
    user_id: int
    title: str
    message: str
    types: Optional[List[str]] = None

class NotificationCreate(NotificationBase):
    pass

class Notification(NotificationBase):
    id: int
    status: str
    created_at: datetime

    class Config:
        orm_mode = True
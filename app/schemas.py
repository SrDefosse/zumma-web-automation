from pydantic import BaseModel
from typing import List, Optional

class TaskCreate(BaseModel):
    task_id: str
    lookup_key: Optional[str] = None

class ProductOut(BaseModel):
    name: str
    price: str
    description: str
    image_url: str

class TaskStatus(BaseModel):
    status: str
    data: Optional[List[ProductOut]] = None
    error_message: Optional[str] = None

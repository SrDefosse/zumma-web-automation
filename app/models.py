# app/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Text, Enum, Numeric
import enum, uuid
from datetime import datetime
from decimal import Decimal

class Base(DeclarativeBase):
    pass

class JobStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"

class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    lookup_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)

    # campos de precio
    price_text: Mapped[str] = mapped_column(String(100))
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

class ProductImage(Base):
    __tablename__ = "product_images"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    file_path: Mapped[str] = mapped_column(String(255))
    served_url: Mapped[str] = mapped_column(String(255))
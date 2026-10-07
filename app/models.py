import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.completed, JobStatus.failed)


job_status_enum = Enum(
    JobStatus,
    name="job_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class TimestampMixin:
    """created_at / updated_at con timezone y defaults del lado de la base de datos."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Site(Base, TimestampMixin):
    """Sitio soportado. El `code` es el task_id que recibe la API."""

    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="site")


class Job(Base, TimestampMixin):
    """Una ejecucion de scraping."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    lookup_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        job_status_enum, default=JobStatus.pending, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    site: Mapped[Site] = relationship(back_populates="jobs")
    products: Mapped[list["Product"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Product(Base, TimestampMixin):
    """Producto extraido, normalizado.

    `price_text` conserva el valor tal como lo publica el sitio (es lo que devuelve la API);
    `price_amount` y `price_currency` son la version normalizada para poder consultar y comparar.
    """

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("job_id", "name", name="uq_products_job_name"),
        Index("ix_products_job_id", "job_id"),
        Index("ix_products_site_id_name", "site_id", "name"),
        CheckConstraint(
            "price_amount IS NULL OR price_amount >= 0", name="ck_products_price_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    price_text: Mapped[str] = mapped_column(String(100), nullable=False)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    job: Mapped[Job] = relationship(back_populates="products")
    image: Mapped["ProductImage | None"] = relationship(
        back_populates="product", cascade="all, delete-orphan", uselist=False
    )


class ProductImage(Base, TimestampMixin):
    """Imagen descargada y servida por este backend."""

    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)

    product: Mapped[Product] = relationship(back_populates="image")

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

DEFAULT_DB_URL = os.environ.get(
    "SDIE_DATABASE_URL",
    "sqlite:///data/sdie_v33.db",
)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    project_id = Column(String(64), unique=True, nullable=False)
    name = Column(String(256))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    drawings = relationship("Drawing", back_populates="project")


class Drawing(Base):
    __tablename__ = "drawings"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    filename = Column(String(512), nullable=False)
    processed_at = Column(DateTime)
    project = relationship("Project", back_populates="drawings")
    components = relationship("Component", back_populates="drawing")
    quantities = relationship("Quantity", back_populates="drawing")


class Component(Base):
    __tablename__ = "components"
    id = Column(Integer, primary_key=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id"))
    component_id = Column(String(64), nullable=False)
    component_type = Column(String(64))
    layer = Column(String(128))
    confidence = Column(Float)
    payload = Column(JSON)
    drawing = relationship("Drawing", back_populates="components")


class AtlasSampleRow(Base):
    __tablename__ = "atlas_samples"
    id = Column(Integer, primary_key=True)
    sample_id = Column(String(128), unique=True)
    project_id = Column(String(64))
    component_type = Column(String(64))
    source_drawing = Column(String(512))
    payload = Column(JSON)


class Quantity(Base):
    __tablename__ = "quantities"
    id = Column(Integer, primary_key=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id"))
    slab_id = Column(String(64))
    area_m2 = Column(Float)
    concrete_m3 = Column(Float)
    shuttering_m2 = Column(Float)
    payload = Column(JSON)
    drawing = relationship("Drawing", back_populates="quantities")


def get_engine(db_url: str | None = None):
    return create_engine(db_url or DEFAULT_DB_URL, future=True)


def init_db(db_url: str | None = None):
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

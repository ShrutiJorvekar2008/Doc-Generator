"""SQLAlchemy models: sessions, messages, artifacts (versioned files), sources."""
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from .config import settings

kw = {"connect_args": {"check_same_thread": False}} if settings.DATABASE_URL.startswith("sqlite") else {"pool_pre_ping": True}
engine = create_engine(settings.DATABASE_URL, **kw)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def uid() -> str:
    return uuid.uuid4().hex


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(String(32), primary_key=True, default=uid)
    title = Column(String(200), default="New chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.id")
    artifacts = relationship("Artifact", back_populates="session", cascade="all, delete-orphan", order_by="Artifact.created_at")


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), ForeignKey("chat_sessions.id"), index=True)
    role = Column(String(20))  # user | assistant
    content = Column(Text)
    sources = Column(JSON, default=list)       # citations used for this answer
    artifact_id = Column(String(32), nullable=True)  # file produced by this turn
    created_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("ChatSession", back_populates="messages")


class Artifact(Base):
    __tablename__ = "artifacts"
    id = Column(String(32), primary_key=True, default=uid)
    session_id = Column(String(32), ForeignKey("chat_sessions.id"), index=True)
    name = Column(String(255))
    kind = Column(String(10))              # docx | pptx | xlsx | txt | md | pdf
    role = Column(String(12), default="template")  # template | reference | output
    version = Column(Integer, default=1)
    parent_id = Column(String(32), nullable=True)
    path = Column(String(500))
    analysis = Column(JSON, nullable=True)
    change_log = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("ChatSession", back_populates="artifacts")


def init_db():
    Base.metadata.create_all(engine)

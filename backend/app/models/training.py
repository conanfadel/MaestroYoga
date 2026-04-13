from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class TrainingExercise(Base):
    __tablename__ = "training_exercises"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    muscle_key = Column(String(64), nullable=False, index=True)
    exercise_name = Column(String(180), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    center = relationship("Center")


class TrainingAssignmentBatch(Base):
    __tablename__ = "training_assignment_batches"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(Integer, ForeignKey("yoga_sessions.id"), nullable=True, index=True)
    title = Column(String(180), nullable=True)
    notes = Column(Text, nullable=True)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    status = Column(String(24), nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    center = relationship("Center")
    client = relationship("Client")
    assigned_by_user = relationship("User")
    session = relationship("YogaSession")


class TrainingAssignmentItem(Base):
    __tablename__ = "training_assignment_items"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("training_assignment_batches.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    exercise_id = Column(Integer, ForeignKey("training_exercises.id"), nullable=True, index=True)
    muscle_key = Column(String(64), nullable=False, index=True)
    exercise_name = Column(String(180), nullable=False)
    sets_count = Column(Integer, nullable=True)
    reps_text = Column(String(64), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    rest_seconds = Column(Integer, nullable=True)
    intensity_text = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    center = relationship("Center")
    batch = relationship("TrainingAssignmentBatch")
    client = relationship("Client")
    exercise = relationship("TrainingExercise")


class ClientMedicalProfile(Base):
    __tablename__ = "client_medical_profiles"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    chronic_conditions = Column(Text, nullable=True)
    current_medications = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    injuries_history = Column(Text, nullable=True)
    surgeries_history = Column(Text, nullable=True)
    contraindications = Column(Text, nullable=True)
    emergency_contact_name = Column(String(120), nullable=True)
    emergency_contact_phone = Column(String(40), nullable=True)
    coach_notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow_naive, nullable=False)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    center = relationship("Center")
    client = relationship("Client")


class ClientMedicalHistoryEntry(Base):
    __tablename__ = "client_medical_history_entries"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True, default="condition")
    title = Column(String(180), nullable=False)
    details = Column(Text, nullable=True)
    event_date = Column(DateTime, nullable=True)
    severity = Column(String(32), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

    center = relationship("Center")
    client = relationship("Client")
    created_by_user = relationship("User")

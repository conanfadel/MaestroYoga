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

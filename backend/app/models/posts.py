from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class CenterPost(Base):
    """أخبار، إعلانات، رحلات، مسابقات، تقارير مصورة — للواجهة العامة."""

    __tablename__ = "center_posts"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    post_type = Column(String(32), nullable=False, index=True)
    title = Column(String(220), nullable=False)
    summary = Column(String(600), nullable=True)
    body = Column(Text, nullable=True)
    cover_image_url = Column(String, nullable=True)
    is_published = Column(Boolean, nullable=False, default=False, index=True)
    is_pinned = Column(Boolean, nullable=False, default=False, index=True)
    published_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    center = relationship("Center", back_populates="posts")
    images = relationship(
        "CenterPostImage",
        back_populates="post",
        order_by="CenterPostImage.sort_order",
        cascade="all, delete-orphan",
    )


class CenterPostImage(Base):
    __tablename__ = "center_post_images"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("center_posts.id"), nullable=False, index=True)
    image_url = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow_naive)

    post = relationship("CenterPost", back_populates="images")

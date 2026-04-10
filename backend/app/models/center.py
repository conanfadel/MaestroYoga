from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class Center(Base):
    __tablename__ = "centers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    city = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    brand_tagline = Column(String, nullable=True)
    hero_image_url = Column(String, nullable=True)
    # عند عدم رفع غلاف: True = صورة يوغا افتراضية (ثيم التطبيق)، False = تدرج ألوان فقط
    hero_show_stock_photo = Column(Boolean, nullable=False, default=True)
    # برنامج الولاء (اختياري): NULL = استخدام عتبات متغيرات البيئة LOYALTY_*_MIN_CONFIRMED
    loyalty_bronze_min = Column(Integer, nullable=True)
    loyalty_silver_min = Column(Integer, nullable=True)
    loyalty_gold_min = Column(Integer, nullable=True)
    loyalty_label_bronze = Column(String(64), nullable=True)
    loyalty_label_silver = Column(String(64), nullable=True)
    loyalty_label_gold = Column(String(64), nullable=True)
    loyalty_reward_bronze = Column(Text, nullable=True)
    loyalty_reward_silver = Column(Text, nullable=True)
    loyalty_reward_gold = Column(Text, nullable=True)
    # إعدادات محتوى صفحة الحجز العامة (JSON): أقسام، إظهار/إخفاء، نصوص مخصصة
    index_config_json = Column(Text, nullable=True)
    # أهداف تقارير شهرية (اختياري) وضريبة العرض لكل مركز ووجهة ملخص بريدي
    monthly_revenue_goal = Column(Float, nullable=True)
    monthly_bookings_goal = Column(Integer, nullable=True)
    vat_rate_percent = Column(Float, nullable=True)
    report_digest_email = Column(String(220), nullable=True)

    clients = relationship("Client", back_populates="center")
    plans = relationship("SubscriptionPlan", back_populates="center")
    rooms = relationship("Room", back_populates="center")
    sessions = relationship("YogaSession", back_populates="center")
    users = relationship("User", back_populates="center")
    faqs = relationship("FAQItem", back_populates="center")
    posts = relationship("CenterPost", back_populates="center")

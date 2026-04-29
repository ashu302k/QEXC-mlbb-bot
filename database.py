from sqlalchemy import create_engine, Column, Integer, String, Boolean, BigInteger, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import DATABASE_URL
from datetime import datetime

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

RARITY_PRICES = {
    "🟢 Обычный": 100,
    "🔵 Исключительный": 200,
    "🟣 Роскошный": 400,
    "🟡 Изысканный": 2000,
    "🟠 Изящный": 3000,
    "🔴 Легендарный": 4000,
}

class Hero(Base):
    __tablename__ = "heroes"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)
    role = Column(String)
    lane = Column(String)

class Skin(Base):
    __tablename__ = "skins"
    id = Column(Integer, primary_key=True)
    hero_id = Column(Integer, ForeignKey("heroes.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, unique=True, index=True)
    rarity = Column(String)
    price = Column(Integer)
    image_file_id = Column(String, nullable=True)
    clean_image_file_id = Column(String, nullable=True)  # Чистое фото для профиля
    hero = relationship("Hero", backref="skins")

    def __init__(self, hero_id, name, rarity, image_file_id=None, clean_image_file_id=None):
        self.hero_id = hero_id
        self.name = name
        self.rarity = rarity
        self.price = RARITY_PRICES.get(rarity, 100)
        self.image_file_id = image_file_id
        self.clean_image_file_id = clean_image_file_id

class SkinRepeat(Base):
    __tablename__ = "skin_repeats"
    skin_id = Column(Integer, ForeignKey("skins.id", ondelete="CASCADE"), primary_key=True)
    repeat_image_file_id = Column(String)
    skin = relationship("Skin", backref="repeat_photo")

class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)
    html_template = Column(String)

class GroupSettings(Base):
    __tablename__ = "group_settings"
    id = Column(Integer, primary_key=True)
    group_id = Column(BigInteger, unique=True, index=True)
    welcome_enabled = Column(Boolean, default=False)
    welcome_message = Column(String, default="Добро пожаловать в чат Mobile Legends!")
    auto_clean_commands = Column(Boolean, default=False)

class UserPrefs(Base):
    __tablename__ = "user_prefs"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, index=True)
    group_id = Column(BigInteger, index=True)
    favorite_hero = Column(String, nullable=True)

class SkinUser(Base):
    __tablename__ = "skin_users"
    user_id = Column(BigInteger, primary_key=True)
    vip_level = Column(Integer, default=0)
    collector_points = Column(Integer, default=0)
    last_skin_time = Column(Integer, default=0)
    equipped_skin_id = Column(Integer, ForeignKey("skins.id", ondelete="SET NULL"), nullable=True)
    equipped_skin = relationship("Skin")

class SkinInventory(Base):
    __tablename__ = "skin_inventory"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, index=True)
    skin_id = Column(Integer, ForeignKey("skins.id", ondelete="CASCADE"))
    skin = relationship("Skin")

class SkinLog(Base):
    __tablename__ = "skin_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, index=True)
    skin_id = Column(Integer, ForeignKey("skins.id", ondelete="CASCADE"))
    timestamp = Column(Integer, default=lambda: int(datetime.now().timestamp()))
    is_repeat = Column(Integer, default=0)
    skin = relationship("Skin")

class Admin(Base):
    __tablename__ = "admins"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, index=True)
    cached_name = Column(String, nullable=True)

class AdminLog(Base):
    __tablename__ = "admin_logs"
    id = Column(Integer, primary_key=True)
    admin_id = Column(BigInteger, index=True)
    action = Column(String)
    target_id = Column(BigInteger, nullable=True)
    target_name = Column(String, nullable=True)
    timestamp = Column(Integer, default=lambda: int(datetime.now().timestamp()))

# Создаём все таблицы
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

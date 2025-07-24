from sqlalchemy import Column, Integer, String, Float, DateTime
from db import Base
from datetime import datetime

class WeatherRecord(Base):
    __tablename__ = "weather"

    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    temperature = Column(Float)
    windspeed = Column(Float)
    time = Column(DateTime, default=datetime.utcnow)
import os
import json
import pandas as pd
import psycopg2
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError

DATABASE_URL = "postgresql+psycopg2://postgres:postgres@postgres/lr_3_test_1"
engine = create_engine(DATABASE_URL, echo=True)
Base = declarative_base()

class DBUser(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    age = Column(Integer, nullable=True)

Base.metadata.create_all(bind=engine)

json_file_name = "users_data_30.json"
json_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), json_file_name)

df = pd.read_json(json_file_path)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()

def insert_users_from_df(df):
    for _, row in df.iterrows():
        age_val = row["age"]
        if pd.notnull(age_val):
            age_val = int(age_val)
        else:
            age_val = None

        user = DBUser(
            id=row["id"],
            username=row["username"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            age=age_val
        )
        session.add(user)
    session.commit()

insert_users_from_df(df)

session.close()
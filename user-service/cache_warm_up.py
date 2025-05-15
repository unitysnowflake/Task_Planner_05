import os
import json
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from user_service import DBUser, Base  # используем те же модели
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Подключение к БД
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres/lr_3_test_1")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

# Подключение к Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://cache:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

def warm_up_cache():
    users = db.query(DBUser).all()
    for user in users:
        user_data = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "age": user.age
        }
        # По ID
        redis_client.set(f"user:{user.id}", json.dumps(user_data), ex=180)
        # По username
        redis_client.set(f"user:{user.username}", json.dumps(user_data), ex=180)
    print(f"Загружено пользователей: {len(users)}")

if __name__ == "__main__":
    warm_up_cache()
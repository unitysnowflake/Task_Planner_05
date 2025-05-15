import os
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import create_engine, Column, Integer, String, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import redis
import json

# Конфиг JWT
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Настройка SQLAlchemy
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres/lr_3_test_1")
engine = create_engine(DATABASE_URL)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Используем или не используем кэш для тестирования
USE_REDIS = os.getenv("USE_REDIS", "true") == "true"

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Таблица с пользователями в БД
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# валидация
class UserBase(BaseModel):
    username: str = Field(..., example="anna_ivanova")
    first_name: str = Field(..., example="Anna")
    last_name: str = Field(..., example="Ivanova")
    email: str = Field(..., example="anna.iva@example.ru")
    age: Optional[int] = Field(None, example=30)

class UserCreate(UserBase):
    id: int
    password: str = Field(..., example="password123")

# Ответ API (без пароля)
class User(UserBase):
    id: int
    
    class Config:
        orm_mode = True

class UserUpdate(UserBase):
    password: Optional[str] = Field(None, example="password123")


app = FastAPI()

# Мастер пользователь
client_db = {
    "admin": "$argon2id$v=19$m=65536,t=3,p=4$j1Eq5Zxz7t27t/b+P2eMcQ$Y+ilCKKYNBAZ91CxXWFM5kjMJ8XA2gmC9S+aCcwt50A" # хэшированный пароль
}

# Настройка паролей
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Настройка OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_client(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

async def get_current_user(username: str = Depends(get_current_client), db: Session = Depends(get_db)):
    if username in client_db:
        return {"username": username, "is_admin": True}
    
    user = db.query(DBUser).filter(DBUser.username == username).first()
    if user is None:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

# Возврат токена
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Запрос на создание токена для пользователя
@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    username_to_check = form_data.username
    password_to_verify = form_data.password

    stored_password_hash = None
    is_admin = False

    if username_to_check in client_db:
        stored_password_hash = client_db[username_to_check]
        is_admin = True
    else:
        user_in_db = db.query(DBUser).filter(DBUser.username == username_to_check).first()

        if user_in_db:
            stored_password_hash = user_in_db.hashed_password
        else:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="username is incorrect",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if not pwd_context.verify(password_to_verify, stored_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username_to_check}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# CRUD для пользователей
# Получение всех пользователей
@app.get("/users", response_model=List[User])
def get_users(
    db: Session = Depends(get_db),
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    query: Optional[str] = None,
    current_authenticated_user: dict = Depends(get_current_user)
):

    db_query = db.query(DBUser)

    if query:
        db_query = db_query.filter(
            or_(
                DBUser.first_name.ilike(f"%{query}%"),
                DBUser.last_name.ilike(f"%{query}%")
            )
        )
    elif first_name or last_name:
        if first_name:
            db_query = db_query.filter(DBUser.first_name.ilike(f"%{first_name}%"))
        if last_name:
            db_query = db_query.filter(DBUser.last_name.ilike(f"%{last_name}%"))

    users = db_query.all()
    return users

# Получеине по ID с кэшированием
@app.get("/users/{user_id}", response_model=User)
def get_user_by_id(user_id: int, db: Session = Depends(get_db), current_authenticated_user: dict = Depends(get_current_user)):
    # Если кэш включен то выполняем запрос к нему
    if USE_REDIS:
        cache_key = f"user:{user_id}"
        if redis_client.exists(cache_key):
            cached_user = redis_client.get(cache_key)
            return json.loads(cached_user)
        else:
            # Если кэш не найден, выполняем запрос к БД
            user = db.query(DBUser).filter(DBUser.id == user_id).first()
            user_json = dict()
            for k in user.__dict__:
                if k != '_sa_instance_state':
                    user_json[k] = user.__dict__[k]

            if user:
                redis_client.set(cache_key, json.dumps(user_json), ex=180)
            else:
                raise HTTPException(status_code=404, detail="User not found")
            return user
    else:
        # Если кэш отключен, сразу выполняем запрос к БД
        user = db.query(DBUser).filter(DBUser.id == user_id).first()
        if user:
            return user
        else:
            raise HTTPException(status_code=404, detail="User not found")

# Получение по username с кэшированием
@app.get("/users/by-username/{username}", response_model=User)
def get_user_by_username(username: str, db: Session = Depends(get_db), current_authenticated_user: dict = Depends(get_current_user)):
    # Если кэш включен то выполняем запрос к нему
    if USE_REDIS:
        cache_key = f"user:{username}"
        if redis_client.exists(cache_key):
            cached_user = redis_client.get(cache_key)
            return json.loads(cached_user)
        else:
            # Если кэш не найден, выполняем запрос к БД
            user = db.query(DBUser).filter(DBUser.username == username).first()
            user_json = dict()
            for k in user.__dict__:
                if k != '_sa_instance_state':
                    user_json[k] = user.__dict__[k]

            if user:
                redis_client.set(cache_key, json.dumps(user_json), ex=180)
            else:
                raise HTTPException(status_code=404, detail="User not found")
            return user
    else:
        # Если кэш отключен, сразу выполняем запрос к БД
        user = db.query(DBUser).filter(DBUser.username == username).first()
        if user:
            return user
        else:
            raise HTTPException(status_code=404, detail="User not found")

# Создание пользователя с проверками на ID и username других пользователей, добавление в БД
@app.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db), current_authenticated_user: dict = Depends(get_current_user)):
    db_user_exists = db.query(DBUser).filter(
        or_(DBUser.id == user.id, DBUser.username == user.username)
    ).first()

    if db_user_exists:
        if db_user_exists.id == user.id:
             detail = f"User with this iD already exists"
        elif db_user_exists.username == user.username:
             detail = f"This username already exists"
             
        raise HTTPException(status_code=400, detail=detail)

    hashed_password = pwd_context.hash(user.password)

    db_user = DBUser(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        hashed_password=hashed_password,
        age=user.age
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user

# Обновление полей пользователей с проверками на схожесть полей для других пользователей
@app.put("/users/{user_id}", response_model=User)
def update_user(user_id: int, updated_user: UserUpdate, db: Session = Depends(get_db), current_authenticated_user: dict = Depends(get_current_user)):
    db_user = db.query(DBUser).filter(DBUser.id == user_id).first()

    if updated_user.username and updated_user.username != db_user.username:
        existing_user = db.query(DBUser).filter(DBUser.username == updated_user.username).first()

        if existing_user:
             raise HTTPException(status_code=400, detail=f"This username already exists")
             
    if updated_user.email and updated_user.email != db_user.email:
        existing_user = db.query(DBUser).filter(DBUser.email == updated_user.email).first()

        if existing_user:
             raise HTTPException(status_code=400, detail=f"This Email already exists")

    for field, value in updated_user.model_dump(exclude_unset=True).items():
        if field == "password":
            if value:
                setattr(db_user, "hashed_password", pwd_context.hash(value))
        else:
            setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)

    return db_user

#Удаление пользователей
@app.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(user_id: int, db: Session = Depends(get_db), current_authenticated_user: dict = Depends(get_current_user)):
    db_user = db.query(DBUser).filter(DBUser.id == user_id).first()

    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(db_user)
    db.commit()

    return {"message": f"User deleted succesfuly"}
from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from jose import JWTError, jwt
import requests
from requests.exceptions import RequestException
from pymongo import MongoClient

# База данных
MONGO_DETAILS = "mongodb://mongodb:27017"
client = MongoClient(MONGO_DETAILS)
db = client.goal_tracker_db
goals_collection = db.goals
tasks_collection = db.tasks

# Индексы для полей
goals_collection.create_index("title")
tasks_collection.create_index("goal_id")
tasks_collection.create_index("assignee")
tasks_collection.create_index("status")
tasks_collection.create_index("description")

# Конфиг JWT
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://127.0.0.1:8001/token")

USER_SERVICE_URL = "http://user-service:8001"

app = FastAPI()

# Валидация для целей
class GoalBase(BaseModel):
    title: str
    description: str

class GoalCreate(GoalBase):
    id: int

class Goal(GoalBase):
    id: int = Field(..., alias="_id")

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

# Валидация для задач
class TaskBase(BaseModel):
    title: str
    description: str
    status: str
    assignee: str

class TaskCreate(TaskBase):
    id: int

class Task(TaskBase):
    id: int = Field(..., alias="_id")
    goal_id: int

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

# Получение пользователя из токена
def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Couldn't validate this user",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")

        if username is None:
            raise credentials_exception
        return {"username": username, "token": token}
    
    except JWTError:
        raise credentials_exception

# Проверка существования пользователя для эндпоинтов (через requests с user-service)
def user_exists(username: str, token: str) -> bool:
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{USER_SERVICE_URL}/users/by-username/{username}", headers=headers, timeout=5)

    return response.status_code == 200

# Эндпоинты CRUD для целей
# Создать цель
@app.post("/goals", response_model=Goal, status_code=status.HTTP_201_CREATED)
def create_goal(goal_in: GoalCreate, current_user: dict = Depends(get_current_user)):
    if goals_collection.find_one({"_id": goal_in.id}):
        raise HTTPException(status_code=400, detail="Goal with this ID already exists")

    goal_doc = goal_in.dict(by_alias=True)
    goal_doc["_id"] = goal_in.id
    goals_collection.insert_one(goal_doc)

    return Goal(**goal_doc)

#Получить все цели
@app.get("/goals", response_model=List[Goal])
def get_goals(current_user: dict = Depends(get_current_user)):
    return [Goal(**doc) for doc in goals_collection.find({}, {"_id": 1, "title": 1, "description": 1})]

#Обновление цели
@app.put("/goals/{goal_id}", response_model=Goal)
def update_goal(goal_id: int, goal_update: GoalBase, current_user: dict = Depends(get_current_user)):
    result = goals_collection.update_one({"_id": goal_id}, {"$set": goal_update.dict(exclude_unset=True)})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    return Goal(**goals_collection.find_one({"_id": goal_id}))

#Получить цель по ID
@app.get("/goals/{goal_id}", response_model=Goal)
def get_goal(goal_id: int, current_user: dict = Depends(get_current_user)):
    doc = goals_collection.find_one({"_id": goal_id})

    if doc:
        return Goal(**doc)
    raise HTTPException(status_code=404, detail="Goal not found")

#Удаление цели
@app.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, current_user: dict = Depends(get_current_user)):
    tasks_collection.delete_many({"goal_id": goal_id})
    result = goals_collection.delete_one({"_id": goal_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")

# Эндпоинты CRUD для задач
# Создать задачу для цели
# Задачи создаются под цели и под исполнителя одновременно, поэтому они оба должны существовать
# Токен должен быть не просрочен
@app.post("/goals/{goal_id}/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task_for_goal(goal_id: int, task_in: TaskCreate, current_user: dict = Depends(get_current_user)):

    if not goals_collection.find_one({"_id": goal_id}):
        raise HTTPException(status_code=404, detail="Goal not found")
    
    if not user_exists(task_in.assignee, current_user["token"]):
        raise HTTPException(status_code=400, detail="Assignee not found")
    
    if tasks_collection.find_one({"_id": task_in.id}):
        raise HTTPException(status_code=400, detail="A task with this ID already exists")

    task_doc = task_in.dict(by_alias=True)
    task_doc["_id"] = task_in.id
    task_doc["goal_id"] = goal_id
    tasks_collection.insert_one(task_doc)

    return Task(**task_doc)

# Получить все задачи у ID цели и поиск с query статуса и/или описания задачи (незавимисо друг от друга с любым регистром в описании)
@app.get("/goals/{goal_id}/tasks", response_model=List[Task])
def get_tasks_for_goal(
    goal_id: int,
    status: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    if not goals_collection.find_one({"_id": goal_id}):
        raise HTTPException(status_code=404, detail="Goal not found")

    query = {"goal_id": goal_id}

    if status:
        query["status"] = status

    if description:
        query["description"] = {"$regex": description, "$options": "i"}

    return [Task(**doc) for doc in tasks_collection.find(query)]

# Получить задачу по ID задачи
@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: int, current_user: dict = Depends(get_current_user)):
    doc = tasks_collection.find_one({"_id": task_id})

    if doc:
        return Task(**doc)
    raise HTTPException(status_code=404, detail="Task not found")

# Обновление задачи
# Пользователь должен существовать для обновления задачи (так же как и при создании)
# Токен должен быть не просрочен
@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, task_update: TaskBase, current_user: dict = Depends(get_current_user)):
    token = current_user["token"]
    existing = tasks_collection.find_one({"_id": task_id})

    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task_update.assignee != existing.get("assignee"):
        if not user_exists(task_update.assignee, token):
            raise HTTPException(status_code=400, detail="New assignee not found")
    tasks_collection.update_one({"_id": task_id}, {"$set": task_update.dict(exclude_unset=True)})

    return Task(**tasks_collection.find_one({"_id": task_id}))

# Удаление задачи
@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, current_user: dict = Depends(get_current_user)):
    result = tasks_collection.delete_one({"_id": task_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
import os
import json
from pymongo import MongoClient

MONGO_DETAILS = "mongodb://mongodb:27017"
client = MongoClient(MONGO_DETAILS)
db = client.goal_tracker_db

dir = os.path.dirname(os.path.abspath(__file__))

goals = os.path.join(dir, 'goals.json')
tasks = os.path.join(dir, 'tasks.json')

def initialize_db():
    try:
        with open(goals, "r") as f:
            goals_data = json.load(f)
        with open(tasks, "r") as f:
            tasks_data = json.load(f)
    except FileNotFoundError:
        print("json files not found")
        return

    goals_collection = db.goals
    tasks_collection = db.tasks

    if goals_collection.count_documents({}) == 0:
        goals_collection.insert_many(goals_data)
        print("Goals data imported.")
    else:
        print("Goals data already exists")

    if tasks_collection.count_documents({}) == 0:
        tasks_collection.insert_many(tasks_data)
        print("Tasks data imported.")
    else:
        print("Tasks data already exists")

initialize_db()

client.close()
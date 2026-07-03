from fastapi import FastAPI
from pydantic import BaseModel
from scam_analyser import scam_detector

app = FastAPI()

# Model for our POST request data
class Item(BaseModel):
    name: str
    price: float

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI app on Render!"}

@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id, "status": "Available"}

@app.post("/items/")
def create_item(item: Item):
    return {"message": "Item created successfully", "data": item}
from fastapi import FastAPI
from pydantic import BaseModel
from digital_scam_shield import scam_detector
# from scam_shield_with_api import analyzer
from scam_analyser import main

app = FastAPI()

# Model for our POST request data
class Item(BaseModel):
    name: str
    price: float

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI app on Render!"}

@app.get("/ScamDetection/")
def read_item():
    print("Model Initialised...")
    result = scam_detector()
    return {"status": result}

@app.get("/ModelTest/")
def read_item():
    print("Model Initialised...")
    result = main()
    return {"status": result}

@app.post("/items/")
def create_item(item: Item):
    return {"message": "Item created successfully", "data": item}
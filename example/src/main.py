"""example/src/main.py"""

from fastapi import FastAPI

# This is the application instance your plugin will discover
app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id}


@app.post("/items")
def create_item(item: dict):
    return {"message": "Item created", "item": item}


@app.put("/items/{item_id}")
def update_item(item_id: int, item: dict):
    return {"message": "Item updated", "item_id": item_id, "item": item}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/xyzzyx")
def xyzzyx():
    return {"message": "This is a test endpoint."}

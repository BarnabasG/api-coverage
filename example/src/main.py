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


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/xyzzyx")
def xyzzyx():
    return {"message": "This is a test endpoint."}

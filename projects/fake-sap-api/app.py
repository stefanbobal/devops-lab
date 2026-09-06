from fastapi import FastAPI

app = FastAPI()

@app.get("/status")
def status():
    return {
        "sid": "D50",
        "application": "UP",
        "database": "DOWN",
        "version": "2.0"
    }

import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/status")
def status():
    return {
        "sid": os.getenv("SAP_SID", "UNKNOWN"),
        "application": os.getenv("APP_STATUS", "UNKNOWN"),
        "database": os.getenv("DB_STATUS", "UNKNOWN"),
        "version": "3.0",
        "user": os.getenv("SAP_USER", "UNKNOWN")
    }
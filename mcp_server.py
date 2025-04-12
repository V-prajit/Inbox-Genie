from fastapi import FastAPI
import os
from dotenv import load_dotenv
import uvicorn
import sys

from routes import router

load_dotenv()

app = FastAPI(title="Inbox genie")

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("mcp_server:app", host="0.0.0.0", port=8000, reload=True)
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import base64
import uvicorn

#File imports
from routes import router

load_dotenv()

app = FastAPI(title="Inbox genie")

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("mcp_server:app", host="0.0.0.0", port=8000, reload=True)
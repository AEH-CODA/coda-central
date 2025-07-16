# python -m venv venv
# venv\Scripts\activate


# FastAPI App with UI Support

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json
import requests
from utils import generate_sparql_from_json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

GRAPHDB_ENDPOINT = "http://localhost:7200/repositories/json_insert_repo/statements"

@app.get("/", response_class=HTMLResponse)
def ui_upload(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/insert_patient_data")
async def insert_patient_data(file: UploadFile = File(...)):
    content = await file.read()
    data = json.loads(content)

    sparql_query = generate_sparql_from_json(data)

    headers = {
        "Content-Type": "application/sparql-update"
    }

    response = requests.post(GRAPHDB_ENDPOINT, data=sparql_query, headers=headers)

    if response.status_code == 204:
        return {"status": "success", "message": "Data inserted into GraphDB."}
    else:
        return {
            "status": "error",
            "code": response.status_code,
            "details": response.text
        }

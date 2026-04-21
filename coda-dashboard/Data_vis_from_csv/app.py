from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import requests
import urllib.parse
import re

app = FastAPI()

GRAPHDB_ENDPOINT = "http://localhost:7200/repositories/medical_data"

# Smart query map for diagnosis, complaint, investigation, and date range
SMART_QUERY_MAP = {
    "diagnosis": """
        PREFIX ex: <http://example.org/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?patient ?visit ?date ?label WHERE {{
          ?visit a ex:Visit ;
                 ex:hasPatient ?patient ;
                 ex:visitDate ?date ;
                 ex:hasDiagnosis ?d .
          ?d rdfs:label ?label .
          FILTER(CONTAINS(LCASE(?label), "{value}"))
        }}
    """,
    "complaint": """
        PREFIX ex: <http://example.org/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?patient ?visit ?date ?label WHERE {{
          ?visit a ex:Visit ;
                 ex:hasPatient ?patient ;
                 ex:visitDate ?date ;
                 ex:hasComplaint ?c .
          ?c rdfs:label ?label .
          FILTER(CONTAINS(LCASE(?label), "{value}"))
        }}
    """,
    "investigation": """
        PREFIX ex: <http://example.org/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?patient ?visit ?date ?label WHERE {{
          ?visit a ex:Visit ;
                 ex:hasPatient ?patient ;
                 ex:visitDate ?date ;
                 ex:hasInvestigation ?i .
          ?i rdfs:label ?label .
          FILTER(CONTAINS(LCASE(?label), "{value}"))
        }}
    """,
    "date_range": """
        PREFIX ex: <http://example.org/>
        SELECT DISTINCT ?patient ?visit ?date WHERE {{
          ?visit a ex:Visit ;
                 ex:hasPatient ?patient ;
                 ex:visitDate ?date .
          FILTER(?date >= "{start}"^^xsd:dateTime && ?date <= "{end}"^^xsd:dateTime)
        }}
    """
}

def resolve_query_from_input(user_input: str) -> str:
    user_input = user_input.strip().lower()

    # Keyword category mapping
    keywords = {
        "diagnosis": ["pdr", "npdr", "brvo", "ar", "dry", "glaucoma"],
        "complaint": ["swelling", "redness", "vision", "followup", "stye", "itching"],
        "investigation": ["oct", "b-scan", "iop", "gonioscopy", "ffa"]
    }

    for category, words in keywords.items():
        if any(word in user_input for word in words):
            return SMART_QUERY_MAP[category].format(value=user_input)

    # Fallback general label search
    return f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?entity ?label WHERE {{
          ?entity rdfs:label ?label .
          FILTER(CONTAINS(LCASE(?label), \"{user_input}\"))
        }}
    """

@app.get("/", response_class=HTMLResponse)
async def search_form():
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial; padding: 20px; }
            input[type=text], input[type=submit] {
                padding: 8px; margin: 5px 0; width: 400px;
            }
        </style>
    </head>
    <body>
        <h2>Medical Knowledge Graph Search</h2>
        <form action="/search" method="post">
            <label>Enter your query (e.g. "PDR", "swelling", "between 2013-10-01 and 2013-12-01"):</label><br>
            <input type="text" name="query_input" placeholder="Search keyword or condition..."><br>
            <input type="submit" value="Search">
        </form>
    </body>
    </html>
    """

@app.post("/search", response_class=HTMLResponse)
async def perform_smart_search(query_input: str = Form(...)):
    sparql = resolve_query_from_input(query_input)

    try:
        params = {"query": sparql}
        url = f"{GRAPHDB_ENDPOINT}?{urllib.parse.urlencode(params)}"
        response = requests.get(url, headers={"Accept": "application/sparql-results+json"})
    except Exception as e:
        return f"<p>Failed to connect to GraphDB: {str(e)}</p>"

    if response.status_code != 200:
        return f"<p>Error: {response.status_code} - {response.text}</p>"

    try:
        data = response.json()
        rows = data["results"]["bindings"]
        if not rows:
            return "<p>No results found.</p><a href='/'>Try another</a>"

        html = f"<p><strong>Total matches: {len(rows)}</strong></p>"
        html += "<table border='1' cellpadding='5'><tr>"
        headers = list(rows[0].keys())
        html += "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
        for row in rows:
            html += "<tr>" + "".join(f"<td>{row[h]['value']}</td>" for h in headers) + "</tr>"
        html += "</table><br><a href='/'>Run another query</a>"
        return html
    except Exception as e:
        return f"<p>Error parsing response: {str(e)}</p><a href='/'>Back</a>"

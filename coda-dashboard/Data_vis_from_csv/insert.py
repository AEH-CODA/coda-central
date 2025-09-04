import requests
import pandas as pd

# Read your CSV
df = pd.read_csv("C:\\Users\\DELL\\Downloads\\Arvind Eye Hospital\\CODA\\GraphDB_API\\Hack week\\Patient_Data.csv")

# Clean up missing values
df.fillna("", inplace=True)

GRAPHDB_ENDPOINT = "http://localhost:7200/repositories/medical_data/statements"
PREFIX = "http://example.org/"

import re

def sanitize(s):
    # Remove or replace special characters
    s = re.sub(r'[^a-zA-Z0-9_]', '_', s.strip())
    # Prefix with 'X_' if it starts with a digit
    if re.match(r'^\d', s):
        s = 'X_' + s
    return s

headers = {
    'Content-Type': 'application/sparql-update'
}

triples = []

for idx, row in df.iterrows():
    visit_uri = f"ex:Visit_{row['peid']}_{sanitize(row['pedate'])}"
    patient_uri = f"ex:Patient_{sanitize(row['Anonymous_Uid'])}"

    # Basic visit and patient triples
    triples.append(f"{visit_uri} a ex:Visit ;")
    triples.append(f"    ex:hasPatient {patient_uri} ;")
    triples.append(f"    ex:visitDate \"{row['pedate']}\" .")
    # try this to avoid date issue: 
    # triples.append(f'    ex:visitDate "{row["pedate"]}"^^xsd:dateTime .')
    triples.append(f"{patient_uri} a ex:Patient .")

    # Diagnosis
    for diag in str(row['DiagnosisName']).split(";"):
        diag = diag.strip()
        if diag:
            diag_uri = f"ex:{sanitize(diag)}"
            triples.append(f"{diag_uri} a ex:Diagnosis ; rdfs:label \"{diag}\" .")
            triples.append(f"{visit_uri} ex:hasDiagnosis {diag_uri} .")
            # has value should also be there

    # Investigation
    if row['investicationName']:
        inv = row['investicationName'].strip()
        inv_uri = f"ex:{sanitize(inv)}"
        triples.append(f"{inv_uri} a ex:Investigation ; rdfs:label \"{inv}\" .")
        triples.append(f"{visit_uri} ex:hasInvestigation {inv_uri} .")

    # Complaints
    for comp in str(row['complaintName']).split(";"):
        comp = comp.strip()
        if comp:
            comp_uri = f"ex:{sanitize(comp)}"
            triples.append(f"{comp_uri} a ex:Complaint ; rdfs:label \"{comp}\" .")
            triples.append(f"{visit_uri} ex:hasComplaint {comp_uri} .")

# Wrap in PREFIX and INSERT
sparql_insert = f"""
PREFIX ex: <{PREFIX}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

INSERT DATA {{
{chr(10).join(triples)}
}}
"""

# Send request
response = requests.post(GRAPHDB_ENDPOINT, data=sparql_insert.encode("utf-8"), headers=headers)

if response.status_code == 204:
    print("✅ Data inserted successfully into GraphDB.")
else:
    print(f"❌ Error: {response.status_code}\n{response.text}")
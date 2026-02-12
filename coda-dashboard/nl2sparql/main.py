from fastapi import FastAPI # type: ignore
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
import os
import re
from scripts.postprocessing import strip_sparql, header_footer

app = FastAPI(title="NL to SPARQL Service")

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set")

client = Groq(api_key=GROQ_API_KEY)

class NLQuery(BaseModel):
    query: str

@app.post("/translate")
def translate(nl: NLQuery):
    nl_query = nl.query

    prompt = '''You are a system that converts natural language queries into SPARQL queries.

    Rules:
    - Use ONLY the classes and predicates defined below.
    - Do NOT invent new classes or predicates.
    - Generate READ-ONLY SPARQL (SELECT only) and nothing else.
    - Always include LIMIT 10 unless explicitly specified.
    - Output ONLY valid SPARQL or a JSON error object.
    - Return only the final SparQL query. NEVER include your warning messages, reasons or errors.

    Ontology:
    PREFIX : <http://example.org/schema#>

    Classes:
    Patient, Visit, Diagnosis, Complaint, Investigation, Refraction,
    AnteriorSegmentExam, FundusExam, SocialHistory, BirthHistory, SystemicDisease

    Relationships:
    Patient -> hasVisit -> Visit
    Patient -> hasSocialHistory -> SocialHistory
    Patient -> hasBirthHistory -> BirthHistory
    Patient -> hasSystemicDisease -> SystemicDisease
    Visit -> hasDiagnosis -> Diagnosis
    Visit -> hasComplaint -> Complaint
    Visit -> hasInvestigation -> Investigation
    Visit -> hasRefraction -> Refraction
    Visit -> hasAnteriorSegExam -> AnteriorSegmentExam
    Visit -> hasFundusExam -> FundusExam

    Attributes:
    Visit: visitDate
    Diagnosis: diagnosisName
    Complaint: complaintName, complaintSummary, subComplaint, subComplaintValue, eye
    Investigation: investigationName, investigationResult, investigationResultFile
    Refraction: chartType, spectacleType
    AnteriorSegmentExam: part, examValue, examValueQualifier
    SocialHistory: smokingStatus ("Daily", "Frequently", "Rarely", "Never"), alcoholConsumption ("Daily", "Frequently", "Rarely", "Never"), maritalStatus ("Married", "Single", "Divorced", "Widow"), consanginousParents
    BirthHistory: birthWeight, birthMode
    SystemicDisease: diseaseName, prescription, numberOfYears, remarks

    Natural language query:
    '''

    prompt += nl_query

    print("Calling Groq")
    
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You convert natural language to SPARQL."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )

    print("Groq Raw Response: ", response.choices[0].message.content)
    sparql_query = response.choices[0].message.content.strip()

    # SAFETY CHECKS
    sparql_query = strip_sparql(sparql_query)
    print("Stripped SparQL response: ", sparql_query)

    if sparql_query.startswith("{"):
        return {
            "status": "ERROR",
            "reason": sparql_query
        }

    if "SELECT" not in sparql_query.upper():
        return {
            "status": "ERROR",
            "reason": "Model did not return a SELECT query"
        }

    # SOME POST-PROCESSING
    sparql_query = header_footer(sparql_query)
    
    # RETURN
    print("Final SparQL query: ", sparql_query)

    return {
        "sparql": sparql_query,
        "status": "SUCCESS"
    }
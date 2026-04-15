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
    - Output ONLY valid SPARQL or a JSON error object.
    - Return only the final SparQL query. NEVER include your warning messages, reasons or errors.

    Ontology:
    PREFIX ns1: <http://clinical-example.org/ontology/>

    Classes:
    - Patient
    - Visit
    - Complaint
    - Investigation
    - VitalDetails
    - VisionDetails
    - VisionItem
    - RefractionDetails
    - RefractionItem
    - AnteriorSegmentExam
    - ExamFinding
    - ReportedHistory
    - SystemicHistory
    - AdviceDetails

    Relationships:
    - Patient → hasVisit → Visit
    - Patient → hasReportedHistory → ReportedHistory
    - ReportedHistory → hasSystemicHistory → SystemicHistory

    - Visit → hasComplaint → Complaint
    - Visit → hasInvestigation → Investigation
    - Visit → hasVitals → VitalDetails
    - Visit → hasVisionDetails → VisionDetails
    - Visit → hasRefraction → RefractionDetails
    - Visit → hasAsExam → AnteriorSegmentExam
    - Visit → hasAdvice → AdviceDetails

    - VisionDetails → hasVisionItem → VisionItem
    - RefractionDetails → hasRefractionItem → RefractionItem
    - AnteriorSegmentExam → hasFinding → ExamFinding

    Key Attributes:

    Patient:
    - patientId (string)

    Visit:
    - visitDate (date)

    Complaint:
    - complaintName (string)
    - duration (string)

    SystemicHistory:
    - conditionCode (string)
    - duration (string)
    - hasPrescription (boolean)

    Investigation:
    - investigationName (string)
    - resultNumeric (decimal)
    - resultUnit (string)
    - laterality (string)

    VitalDetails:
    - systolicBP (int)
    - diastolicBP (int)

    VisionItem:
    - visionType (string)
    - chartType (string)
    - leftEyeValue (string)
    - rightEyeValue (string)

    ExamFinding:
    - partName (string)
    - findingValue (string)

    RefractionItem:
    - reSphere, reCylinder, reAxis, rePHVA
    - leSphere, leCylinder, leAxis, lePHVA

    Natural language query:
    '''

    prompt += nl_query

    print("Calling Groq")
    
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
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
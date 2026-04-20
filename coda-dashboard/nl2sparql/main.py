from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import logging
from groq import Groq
from scripts.postprocessing import strip_sparql, header_footer
from scripts.ontology_cache import analyze_query_intent, get_primary_classes

app = FastAPI(title="NL to SPARQL Service - Smart Column Selection")

load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GRAPHDB_URL = os.getenv("GRAPHDB_URL")
GRAPHDB_REPO = os.getenv("GRAPHDB_REPO")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set")

groq_client = Groq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NLQuery(BaseModel):
    query: str

def build_smart_prompt(nl_query: str) -> str:
    """Build contextual prompt using ontology intelligence"""
    
    # Analyze the query to understand intent
    query_analysis = analyze_query_intent(nl_query)
    primary_classes = get_primary_classes(nl_query)
    ignore_columns = query_analysis["should_ignore_columns"]
    
    logger.info(f"Query Analysis - Primary classes: {primary_classes}, Ignore: {ignore_columns}")
    
    # Build a minimal, focused prompt
    prompt = f"""You are a SPARQL expert. Generate minimal, efficient SELECT queries ONLY.

IMPORTANT - Query Understanding:
- User asked about: {', '.join(primary_classes)}
- Ignore these redundant columns: {', '.join(ignore_columns) if ignore_columns else 'none'}
- Only select columns that directly answer the question
- Use shortest path through relationships

Replace ID columns with readable data:
- Don't select 'complaint' (raw ID) unless explicitly specified. Instead select 'complaintName' (the actual complaint text)
- Don't select 'visit' (raw ID) unless explicitly specified. Instead select 'visitDate' (when the visit happened)
- Don't select 'investigation' (raw ID) unless explicitly specified. Instead select 'investigationName' (test name)
- Don't select 'vitalDetails' (raw ID) unless explicitly specified. Instead select 'systolicBP' or 'diastolicBP' (actual vital signs)
- Don't select 'visionDetails' (raw ID) unless explicitly specified. Instead select 'visionType' or 'leftEyeValue' (vision data)
- Don't select 'refraction' (raw ID) unless explicitly specified. Instead select 'reSphere', 'reCylinder', etc. (refraction data)
- Don't select 'exam' or 'examId' (raw ID) unless explicitly specified. Instead select 'partName' or 'findingValue' (exam findings)
- Don't select 'advice' (raw ID) unless explicitly specified. Instead select 'drug_name' (medication) or 'procedure_name' (procedure)
- Don't select 'diagnosis' (raw ID) unless explicitly specified. Instead select 'diagnosisName' (diagnosis text)
But you can select these ID columns if the user explicitly asks for them or if they are the only way to answer the question.

Ontology:
PREFIX ns1: <http://clinical-example.org/ontology/>

Classes: Patient, Visit, Complaint, Investigation, VitalDetails, VisionDetails, VisionItem, RefractionDetails, RefractionItem, AnteriorSegmentExam, ExamFinding, ReportedHistory, SystemicHistory, AdviceDetails, DrugPrescription, ProcedureAdvice, Diagnosis, OctDetails

Key Relationships:
- Patient hasVisit Visit | hasReportedHistory ReportedHistory | hasOctDetails OctDetails
- Visit hasComplaint Complaint | hasInvestigation Investigation | hasVitals VitalDetails | hasVisionDetails VisionDetails | hasRefraction RefractionDetails | hasAsExam AnteriorSegmentExam | hasDiagnosis Diagnosis | hasAdvice AdviceDetails
- VisionDetails hasVisionItem VisionItem
- RefractionDetails hasRefractionItem RefractionItem
- AnteriorSegmentExam hasFinding ExamFinding
- AdviceDetails hasAdviceItem DrugPrescription | hasAdviceItem ProcedureAdvice
- ReportedHistory hasSystemicHistory SystemicHistory

Minimal Attribute Reference (PREFER THESE):
- Patient: patientId, patientMrnNo
- Visit: visitDate, batch_id, purpose_of_visit
- OctDetails: scan_id
- Complaint: complaintName, duration, laterality
- Investigation: investigationName, resultNumeric, resultUnit, laterality
- VitalDetails: systolicBP, diastolicBP
- VisionItem: visionType, leftEyeValue, rightEyeValue, chartType
- RefractionItem: reSphere, reCylinder, reAxis, leSphere, leCylinder, leAxis
- ExamFinding: partName, findingValue, laterality
- SystemicHistory: conditionCode, duration, diabetesControl, otherAllergies, hasPrescription
- Diagnosis: diagnosisName, laterality
- DrugPrescription: drug_name, dosage, form_type, drug_duration, drug_advice_date
- ProcedureAdvice: procedure_name, procedure_type, procedure_laterality, procedure_done_at, procedure_completion_date, number_of_sittings_advice

User Query: {nl_query}

Return ONLY a valid SPARQL SELECT query. No explanations."""

    return prompt

@app.post("/translate")
def translate(nl: NLQuery):
    nl_query = nl.query
    
    try:
        # Build smart prompt
        prompt = build_smart_prompt(nl_query)
        
        logger.info(f"Processing: {nl_query}")
        
        # Call Groq
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "You are a SPARQL expert generating minimal, efficient queries. Donot select ID-only columns (like 'complaint', 'visit', 'vitalDetails', 'advice', 'diagnosis'), unless specified. Use readable display columns instead (like 'complaintName', 'visitDate', 'systolicBP', 'drug_name', 'diagnosisName'). Include relevant relationships for medications, procedures, diagnoses when queried."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0
        )
        
        sparql_query = response.choices[0].message.content.strip()
        logger.info(f"Generated SPARQL: {sparql_query}")
        
        # Post-process
        sparql_query = strip_sparql(sparql_query)
        
        # Validate
        if sparql_query.startswith("{"):
            return {"status": "ERROR", "reason": sparql_query}
        
        if "SELECT" not in sparql_query.upper():
            return {"status": "ERROR", "reason": "Model did not return a SELECT query"}
        
        sparql_query = header_footer(sparql_query)
        
        return {"sparql": sparql_query, "status": "SUCCESS"}
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "ERROR", "reason": str(e)}

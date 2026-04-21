# SPARQL Generator for Multiple Patients with Auto-ID

from datetime import datetime
import uuid

def sanitize_id(prefix: str, suffix: str):
    return f"{prefix}{suffix}".replace("-", "").replace(" ", "").lower()

def generate_sparql_from_json(data: dict) -> str:
    triples = []

    for patient in data.get("patients", []):
        pid = str(patient["anonymous_urnno"])
        patient_uri = f"med:patient{pid}"
        history_uri = f"med:history{pid}"

        # Systemic history
        systemic = patient["history"]["systemic_history"][0]
        sh_uri = f"med:sh{uuid.uuid4().hex[:6]}"
        triples.append(f'{patient_uri} rdf:type med:Patient ; med:hasHistory {history_uri} .')
        triples.append(f'{history_uri} med:hasSystemicHistory {sh_uri} ; med:hasBirthHistory med:bh{pid} .')

        triples.append(f'{sh_uri} rdf:type med:SystemicHistory ; med:diseaseName "{systemic["disease_name"]}" ; '
                       f'med:numberOfYears "{systemic["number_of_years"]}" ; '
                       f'med:prescription "{systemic["prescription"]}" ; '
                       f'med:remarks "{systemic["remarks"]}" .')

        # Birth history
        birth = patient["history"]["birth history"]
        triples.append(f'med:bh{pid} rdf:type med:BirthHistory ; '
                       f'med:birthWeight "{birth["birthweight"]}" ; '
                       f'med:birthMode "{birth["birthmode"]}" .')

        # Visit(s)
        for visit in patient["visit"]:
            visit_id = sanitize_id("visit", str(uuid.uuid4().hex[:6]))
            visit_uri = f"med:{visit_id}"

            complaint_uri = f"med:complaint{uuid.uuid4().hex[:6]}"
            refraction_uri = f"med:refraction{uuid.uuid4().hex[:6]}"
            spectacles_uri = f"med:spectacles{uuid.uuid4().hex[:6]}"

            visit_date = datetime.strptime(visit["visit_date"], "%d-%m-%Y").strftime("%Y-%m-%d")

            triples.append(f'{patient_uri} med:hasVisit {visit_uri} .')
            triples.append(f'{visit_uri} rdf:type med:Visit ; med:visitDate "{visit_date}" ; '
                           f'med:hasComplaint {complaint_uri} ; '
                           f'med:hasRefraction {refraction_uri} .')

            triples.append(f'{complaint_uri} rdf:type med:Complaint ; '
                           f'med:complaintSummary "{visit["complaint"]["complaint_summary"]}" .')

            spectacles = visit["refraction"]["current spectacles"]
            triples.append(f'{refraction_uri} rdf:type med:Refraction ; '
                           f'med:hasSpectacles {spectacles_uri} .')

            triples.append(f'{spectacles_uri} rdf:type med:Spectacles ; '
                           f'med:type "{spectacles["type"]}" ; '
                           f'med:chartType "{spectacles["chart type"]}" .')

    sparql = "PREFIX med: <http://hospital.org/ontology#>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n\nINSERT DATA {\n"
    sparql += "\n".join("  " + t for t in triples)
    sparql += "\n}"

    return sparql

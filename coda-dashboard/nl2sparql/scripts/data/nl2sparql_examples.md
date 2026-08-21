# NL2SPARQL Example Pairs -- `june-sample`

**50 natural-language <-> SPARQL pairs**, each executed against the live `june-sample` GraphDB repository 
(`http://localhost:7200/repositories/june-sample`) and confirmed to return a correct result set.

Companion machine-readable file: `nl2sparql_examples.json` (same content, structured as a JSON array of 
`{category, nl_query, sparql}` objects) -- this is the RAG retrieval corpus for the NL2SPARQL service. 
**Whenever this file changes, run `python -m scripts.offline.refresh_examples` from the nl2sparql/ 
directory and commit the updated `nl2sparql_examples_embeddings.csv` and `nl2sparql_examples.md`** -- 
the running service loads the CSV at startup and will refuse to start if its row count doesn't match 
this file.

All queries use `PREFIX ns1: <http://clinical-example.org/ontology/>`. See `NL2SPARQL_JUNE_SAMPLE_SCHEMA_REPORT.md` 
(repo root) for the full schema/data-dictionary background these examples are grounded in.

**Known data-sparsity caveat:** `SurgeryAdvice` has exactly 1 instance in the entire repository (patient
`CODA-PT-3B8B2BB5`, diagnosed with Immature cataract). Any query joining a diagnosis to `SurgeryAdvice` is technically
answerable but not statistically meaningful -- treat as "insufficient surgery data", not a real population pattern.
No example pair is included for this to avoid the RAG corpus reinforcing single-instance answers as reliable. Likewise,
`OctDetails.image_eye_laterality` is only populated on 2 of 1907 scans -- treat as effectively unset. Separately, a small
number of `scan_id` values are shared across two different patients/visits in the source data -- this is a genuine
upstream data-quality issue, not a query bug; don't assume scan_id is a reliable unique key.

---

## Patient lookup

**NL:** List all patients with their patient ID, MRN number, age, and gender

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?patientMrnNo ?age ?gender WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:patientMrnNo ?patientMrnNo ;
           ns1:age ?age ;
           ns1:gender ?gender .
}
LIMIT 20
```

**NL:** How many patients are there in total?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT (COUNT(DISTINCT ?patient) as ?patientCount) WHERE {
  ?patient a ns1:Patient .
}
```

**NL:** Show all female patients

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?age WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:gender "F" ;
           ns1:age ?age .
}
LIMIT 20
```

**NL:** How many male patients and how many female patients are there?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?gender (COUNT(?patient) as ?count) WHERE {
  ?patient a ns1:Patient ;
           ns1:gender ?gender .
}
GROUP BY ?gender
```

**NL:** Find patients whose age in years is over 60

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?age WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:age ?age .
  BIND(xsd:integer(REPLACE(?age, "^(\\d+)\\s+Years?.*$", "$1")) AS ?ageYears)
  FILTER(?ageYears > 60)
}
LIMIT 20
```

## Visit lookup

**NL:** List all visits for patient CODA-PT-B1383581 with their visit dates

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?visit ?visitDate WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId "CODA-PT-B1383581" ;
           ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate .
}
ORDER BY ?visitDate
```

**NL:** Show visits that happened between 2025-06-01 and 2025-06-30

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?visitDate WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate .
  FILTER(?visitDate >= "2025-06-01"^^xsd:date && ?visitDate <= "2025-06-30"^^xsd:date)
}
ORDER BY ?visitDate
LIMIT 20
```

**NL:** What are the distinct purposes of visit recorded in the system?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?purpose (COUNT(*) as ?count) WHERE {
  ?visit a ns1:Visit ;
         ns1:purpose_of_visit ?purpose .
}
GROUP BY ?purpose
ORDER BY DESC(?count)
```

**NL:** Show the 10 most recent visits with patient ID and visit date

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?visitDate WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate .
}
ORDER BY DESC(?visitDate)
LIMIT 10
```

## Vitals (blood pressure)

**NL:** Show blood pressure readings for all visits

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?visitDate ?systolicBP ?diastolicBP WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ; ns1:hasVitals ?vitals .
  ?vitals ns1:systolicBP ?systolicBP ; ns1:diastolicBP ?diastolicBP .
}
LIMIT 20
```

**NL:** Find visits where systolic blood pressure was above 140

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?visitDate ?systolicBP WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ; ns1:hasVitals ?vitals .
  ?vitals ns1:systolicBP ?systolicBP .
  FILTER(?systolicBP > 140)
}
ORDER BY DESC(?systolicBP)
LIMIT 20
```

**NL:** What is the average systolic blood pressure across all recorded vitals?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT (AVG(?systolicBP) as ?avgSystolic) WHERE {
  ?vitals a ns1:VitalDetails ;
          ns1:systolicBP ?systolicBP .
}
```

## Diagnosis

**NL:** List patients diagnosed with diabetic macular edema

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?patientId ?visitDate ?laterality WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ; ns1:hasDiagnosis ?diagnosis .
  ?diagnosis ns1:diagnosisName "Diabetic macular edema" ;
             ns1:laterality ?laterality .
}
LIMIT 20
```

**NL:** What are the most common diagnoses across all visits?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?diagnosisName (COUNT(*) as ?count) WHERE {
  ?diagnosis a ns1:Diagnosis ;
             ns1:diagnosisName ?diagnosisName .
}
GROUP BY ?diagnosisName
ORDER BY DESC(?count)
LIMIT 10
```

**NL:** How many patients have a diagnosis affecting both eyes?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT (COUNT(DISTINCT ?patient) as ?patientCount) WHERE {
  ?patient a ns1:Patient ; ns1:hasVisit ?visit .
  ?visit ns1:hasDiagnosis ?diagnosis .
  ?diagnosis ns1:laterality "BE" .
}
```

**NL:** Show all diagnoses recorded during patient CODA-PT-B1383581's visits

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?visitDate ?diagnosisName ?laterality WHERE {
  ?patient a ns1:Patient ; ns1:patientId "CODA-PT-B1383581" ; ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ; ns1:hasDiagnosis ?diagnosis .
  ?diagnosis ns1:diagnosisName ?diagnosisName ; ns1:laterality ?laterality .
}
```

**NL:** For each visit, list the visit date, all diagnoses and all exam finding part names without duplicating rows

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?visitDate ?diagnoses ?examParts WHERE {
  ?visit a ns1:Visit ; ns1:visitDate ?visitDate .
  {
    SELECT ?visit (GROUP_CONCAT(DISTINCT ?diagnosisName; separator=", ") as ?diagnoses) WHERE {
      ?visit ns1:hasDiagnosis ?diagnosis .
      ?diagnosis ns1:diagnosisName ?diagnosisName .
    } GROUP BY ?visit
  }
  {
    SELECT ?visit (GROUP_CONCAT(DISTINCT ?partName; separator=", ") as ?examParts) WHERE {
      ?visit ns1:hasAsExam ?exam .
      ?exam ns1:hasFinding ?finding .
      ?finding ns1:partName ?partName .
    } GROUP BY ?visit
  }
}
LIMIT 10
```

## Investigation (labs/tests)

**NL:** Show IOP (intraocular pressure) readings above 20 mm of Hg

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?visitDate ?resultNumeric ?laterality WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ; ns1:hasInvestigation ?inv .
  ?inv ns1:investigationName "IOP" ; ns1:resultNumeric ?resultNumeric ; ns1:laterality ?laterality .
  FILTER(?resultNumeric > 20)
}
ORDER BY DESC(?resultNumeric)
LIMIT 20
```

**NL:** What investigation types are recorded and how often?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?investigationName (COUNT(*) as ?count) WHERE {
  ?inv a ns1:Investigation ; ns1:investigationName ?investigationName .
}
GROUP BY ?investigationName
ORDER BY DESC(?count)
```

## Vision

**NL:** Show unaided vision (UCVA) values for both eyes

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?leftEyeValue ?rightEyeValue WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasVisionDetails ?vd .
  ?vd ns1:hasVisionItem ?item .
  ?item ns1:visionType "UCVA With PH" ; ns1:leftEyeValue ?leftEyeValue ; ns1:rightEyeValue ?rightEyeValue .
}
LIMIT 20
```

## Refraction

**NL:** Find right eye refraction records where the sphere power is greater than 1.0

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?reSphere ?reCylinder ?reAxis WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasRefraction ?rd .
  ?rd ns1:hasRefractionItem ?item .
  ?item ns1:reSphere ?reSphere ; ns1:reCylinder ?reCylinder ; ns1:reAxis ?reAxis .
  FILTER(xsd:decimal(?reSphere) > 1.0)
}
LIMIT 20
```

## Anterior segment exam findings

**NL:** Show all abnormal (not Normal) findings recorded for the cornea

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?visitDate ?findingValue ?laterality WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ; ns1:hasAsExam ?exam .
  ?exam ns1:hasFinding ?finding .
  ?finding ns1:partName "Cornea" ; ns1:findingValue ?findingValue ; ns1:laterality ?laterality .
  FILTER(?findingValue != "Normal")
}
LIMIT 20
```

## Systemic history

**NL:** List patients with diabetes recorded in their systemic history

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?patientId ?duration WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasReportedHistory ?rh .
  ?rh ns1:hasSystemicHistory ?sh .
  ?sh ns1:conditionCode "Diabetes" ; ns1:duration ?duration .
}
LIMIT 20
```

**NL:** How many patients have both diabetes and hypertension recorded?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT (COUNT(DISTINCT ?patient) as ?count) WHERE {
  ?patient a ns1:Patient ; ns1:hasReportedHistory ?rh .
  ?rh ns1:hasSystemicHistory ?sh1 .
  ?sh1 ns1:conditionCode "Diabetes" .
  ?rh ns1:hasSystemicHistory ?sh2 .
  ?sh2 ns1:conditionCode "Hypertension" .
}
```

## Drug prescriptions

**NL:** Show all prescribed drugs with dosage for patient CODA-PT-B1383581

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?drug_name ?dosage ?form_type WHERE {
  ?patient a ns1:Patient ; ns1:patientId "CODA-PT-B1383581" ; ns1:hasVisit ?visit .
  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:DrugPrescription ;
        ns1:drug_name ?drug_name ; ns1:dosage ?dosage ; ns1:form_type ?form_type .
}
```

**NL:** What are the most commonly prescribed drugs?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?drug_name (COUNT(*) as ?count) WHERE {
  ?item a ns1:DrugPrescription ; ns1:drug_name ?drug_name .
}
GROUP BY ?drug_name
ORDER BY DESC(?count)
LIMIT 10
```

**NL:** For patients with a diagnosis of glaucoma, what medicines were prescribed? Show patient, visit, and full drug details

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT
  ?patient ?patientId ?visit ?visitDate
  ?drug ?drug_name ?dosage ?drug_duration ?form_type ?drug_advice_date
WHERE {
  ?patient rdf:type ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .

  OPTIONAL { ?visit ns1:visitDate ?visitDate . }

  ?visit ns1:hasDiagnosis ?diag ;
         ns1:hasAdvice ?advice .

  ?diag ns1:diagnosisName ?diagnosisName .
    FILTER(CONTAINS(LCASE(STR(?diagnosisName)) , "glaucoma"))

  ?advice ns1:hasAdviceItem ?drug .
  ?drug rdf:type ns1:DrugPrescription .

  OPTIONAL { ?drug ns1:drug_name ?drug_name . }
  OPTIONAL { ?drug ns1:dosage ?dosage . }
  OPTIONAL { ?drug ns1:drug_duration ?drug_duration . }
  OPTIONAL { ?drug ns1:form_type ?form_type . }
  OPTIONAL { ?drug ns1:drug_advice_date ?drug_advice_date . }
}
ORDER BY ?patientId
```

**NL:** Get all distinct drug names prescribed for patients with glaucoma

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?drug_name
WHERE {
  ?patient rdf:type ns1:Patient ;
           ns1:hasVisit ?visit .

  ?visit ns1:hasDiagnosis ?diag ;
         ns1:hasAdvice ?advice .

  ?diag ns1:diagnosisName ?diagnosisName .
    FILTER(CONTAINS(LCASE(STR(?diagnosisName)) , "glaucoma"))

  ?advice ns1:hasAdviceItem ?drug .
  ?drug rdf:type ns1:DrugPrescription ;
        ns1:drug_name ?drug_name .

  FILTER(STRLEN(STR(?drug_name)) > 0)
}
ORDER BY ?drug_name
```

## Procedure advice

**NL:** List patients advised to undergo PRP (retina laser) procedure

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?patientId ?number_of_sittings_advice WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:ProcedureAdvice ;
        ns1:procedure_name "PRP" ;
        ns1:number_of_sittings_advice ?number_of_sittings_advice .
}
LIMIT 20
```

**NL:** Find procedure advice where more than 2 sittings were advised

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?procedure_name ?number_of_sittings_advice WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:ProcedureAdvice ;
        ns1:procedure_name ?procedure_name ;
        ns1:number_of_sittings_advice ?number_of_sittings_advice .
  FILTER(xsd:integer(?number_of_sittings_advice) > 2)
}
LIMIT 20
```

## General advice (glasses)

**NL:** Which patients were advised new glasses (spectacle prescription)?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?patientId ?visitDate WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ; ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:GeneralAdvice ;
        ns1:glass_precription_value ?glassValue .
  FILTER(LCASE(?glassValue) = "true")
}
LIMIT 20
```

**NL:** Of patients diagnosed with presbyopia, how many were advised glasses (GP / spectacle prescription)?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT (COUNT(DISTINCT ?patient) AS ?patientCount)
WHERE {
  ?patient rdf:type ns1:Patient ;
           ns1:hasVisit ?visit .

  ?visit ns1:hasDiagnosis ?diag ;
         ns1:hasAdvice ?advice .

  ?diag ns1:diagnosisName ?diagName .
  FILTER(LCASE(STR(?diagName)) = "presbyopia")

  ?advice ns1:hasAdviceItem ?gpAdvice .
  ?gpAdvice rdf:type ns1:GeneralAdvice ;
            ns1:glass_precription_value ?glassPrescValue .

  FILTER(?glassPrescValue = "True" || ?glassPrescValue = true)
}
```

## Treatment advice

**NL:** List all treatment advice types recorded and their laterality

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?treatment_type ?treatment_laterality WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:TreatmentAdvice ;
        ns1:treatment_type ?treatment_type ;
        ns1:treatment_laterality ?treatment_laterality .
}
```

## Refraction correction advice

**NL:** Show patients advised a refractive correction and what type

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?refractive_correction_type ?refractive_laterality WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:RefractionCorrection ;
        ns1:refractive_correction_type ?refractive_correction_type ;
        ns1:refractive_laterality ?refractive_laterality .
}
```

## Surgery advice

**NL:** Which patients were advised cataract surgery and what implant was planned?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?primary_procedure ?implant WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:SurgeryAdvice ;
        ns1:primary_procedure ?primary_procedure ;
        ns1:implant ?implant .
}
```

## OCT details

**NL:** List OCT scan IDs recorded for patient CODA-PT-B1383581

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?scan_id ?visit_id WHERE {
  ?patient a ns1:Patient ; ns1:patientId "CODA-PT-B1383581" ; ns1:hasVisit ?visit .
  ?visit ns1:hasOctDetails ?oct .
  ?oct ns1:scan_id ?scan_id ; ns1:visit_id ?visit_id .
}
```

**NL:** How many OCT scans have been recorded in total?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>

SELECT (COUNT(?oct) AS ?octScanCount)
WHERE {
  ?oct a ns1:OctDetails .
}
```

**NL:** List patient ID, visit date, and OCT scan ID for visits that had an OCT scan, ordered by visit date

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>

SELECT ?patientId ?visitDate ?scan_id
WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ;
         ns1:hasOctDetails ?oct .
  ?oct ns1:scan_id ?scan_id .
}
ORDER BY ?visitDate
LIMIT 20
```

**NL:** For visits that included an OCT scan, show the scan ID together with any diagnoses recorded during that same visit

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>

SELECT DISTINCT ?patientId ?visitDate ?scan_id ?diagnosisName
WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ;
         ns1:hasOctDetails ?oct ;
         ns1:hasDiagnosis ?diag .
  ?oct ns1:scan_id ?scan_id .
  ?diag ns1:diagnosisName ?diagnosisName .
}
ORDER BY ?patientId
LIMIT 30
```

**NL:** Which patients have had more than one OCT scan, and how many scans does each of them have?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>

SELECT ?patientId (COUNT(DISTINCT ?oct) AS ?octScanCount)
WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .
  ?visit ns1:hasOctDetails ?oct .
}
GROUP BY ?patientId
HAVING (COUNT(DISTINCT ?oct) > 1)
ORDER BY DESC(?octScanCount)
```

**NL:** For patients diagnosed with any form of retinopathy, find their OCT scan IDs and the visit dates the scans were taken on

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>

SELECT DISTINCT ?patientId ?visitDate ?scan_id
WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .
  ?visit ns1:hasDiagnosis ?diag ;
         ns1:hasOctDetails ?oct .
  ?diag ns1:diagnosisName ?diagnosisName .
  FILTER(CONTAINS(LCASE(STR(?diagnosisName)), "retinopathy"))
  ?oct ns1:scan_id ?scan_id ;
       ns1:visit_id ?visit_id .
  OPTIONAL { ?visit ns1:visitDate ?visitDate . }
}
ORDER BY ?patientId
LIMIT 30
```

**NL:** Show all patients, their diagnoses and OCT scans, for people who scanned in September 2025

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?visitDate ?scan_id ?diagnoses
WHERE {
  ?patient a ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?visit .
  ?visit ns1:visitDate ?visitDate ;
         ns1:hasOctDetails ?oct .
  ?oct ns1:scan_id ?scan_id .
  FILTER(?visitDate >= "2025-09-01"^^xsd:date && ?visitDate <= "2025-09-30"^^xsd:date)
  {
    SELECT ?visit (GROUP_CONCAT(DISTINCT ?diagnosisName; separator=", ") AS ?diagnoses) WHERE {
      ?visit ns1:hasDiagnosis ?diag .
      ?diag ns1:diagnosisName ?diagnosisName .
    } GROUP BY ?visit
  }
}
ORDER BY ?patientId
```

## Cohort filtering (patients matching a visit criterion → all their records)

**NL:** Get all visits of patients who had at least one visit with purpose of visit 'Intra Vit Injection' (IVI)

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT 
  ?patient 
  ?patientId 
  ?visit 
  ?visitDate 
  ?purpose_of_visit
  ?procedure_name
  ?procedure_type
WHERE {
  ?patient rdf:type ns1:Patient ;
           ns1:patientId ?patientId ;
           ns1:hasVisit ?injectionVisit .

  ?injectionVisit ns1:purpose_of_visit "Intra Vit Injection" .

  ?patient ns1:hasVisit ?visit .
  OPTIONAL { ?visit ns1:visitDate ?visitDate . }
  OPTIONAL { ?visit ns1:purpose_of_visit ?purpose_of_visit . }

  OPTIONAL {
    ?visit ns1:hasAdvice ?advice .
    ?advice ns1:hasAdviceItem ?procAdvice .
    ?procAdvice rdf:type ns1:ProcedureAdvice .
    OPTIONAL { ?procAdvice ns1:procedure_name ?procedure_name . }
    OPTIONAL { ?procAdvice ns1:procedure_type ?procedure_type . }
  }
}
ORDER BY ?patient ?visit
```

## Fuzzy / keyword text search over free-text fields

**NL:** Find all patients and visits where the procedure name or procedure type is like 'inj' (injection-related procedures)

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT DISTINCT
  ?patient ?patientId ?visit ?visitDate
  ?procedureItem ?procedure_name ?procedure_type
WHERE {
  ?patient rdf:type ns1:Patient ;
           ns1:hasVisit ?visit .
  OPTIONAL { ?patient ns1:patientId ?patientId . }
  OPTIONAL { ?visit ns1:visitDate ?visitDate . }

  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?procedureItem .
  ?procedureItem rdf:type ns1:ProcedureAdvice .

  OPTIONAL { ?procedureItem ns1:procedure_name ?procedure_name . }
  OPTIONAL { ?procedureItem ns1:procedure_type ?procedure_type . }

  FILTER (
    REGEX(LCASE(COALESCE(STR(?procedure_name), "")), "inj") ||
    REGEX(LCASE(COALESCE(STR(?procedure_type), "")), "inj")
  )
}
ORDER BY ?patient ?visit
```

## Multi-hop / cross-entity

**NL:** For patients diagnosed with proliferative diabetic retinopathy, show their blood pressure readings

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?patientId ?systolicBP ?diastolicBP WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
  ?visit ns1:hasDiagnosis ?diagnosis ; ns1:hasVitals ?vitals .
  ?diagnosis ns1:diagnosisName "PDR - proliferative diabetic retinopathy" .
  ?vitals ns1:systolicBP ?systolicBP ; ns1:diastolicBP ?diastolicBP .
}
LIMIT 20
```

**NL:** Show patient age, diagnosis, and prescribed drug together for each visit

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId ?age ?diagnosisName ?drug_name WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:age ?age ; ns1:hasVisit ?visit .
  ?visit ns1:hasDiagnosis ?diagnosis ; ns1:hasAdvice ?advice .
  ?diagnosis ns1:diagnosisName ?diagnosisName .
  ?advice ns1:hasAdviceItem ?item .
  ?item a ns1:DrugPrescription ; ns1:drug_name ?drug_name .
}
LIMIT 20
```

## Aggregation

**NL:** Count the number of visits per patient, showing only patients with more than 1 visit

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?patientId (COUNT(?visit) as ?visitCount) WHERE {
  ?patient a ns1:Patient ; ns1:patientId ?patientId ; ns1:hasVisit ?visit .
}
GROUP BY ?patientId
HAVING (COUNT(?visit) > 1)
ORDER BY DESC(?visitCount)
LIMIT 20
```

**NL:** What is the breakdown of visits by laterality for exam findings on the Lens?

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?laterality (COUNT(*) as ?count) WHERE {
  ?finding a ns1:ExamFinding ;
           ns1:partName "Lens" ;
           ns1:laterality ?laterality .
}
GROUP BY ?laterality
```

**NL:** Find patients who had the same injection procedure done on more than one distinct completion date

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>

SELECT
  ?patient
  ?patientId
  ?procedure_name
  (COUNT(DISTINCT ?procedure_completion_date) AS ?distinctCompletionDates)
  (GROUP_CONCAT(DISTINCT STR(?procedure_completion_date); separator=" | ") AS ?completionDates)
WHERE {
  ?patient a ns1:Patient ;
           ns1:hasVisit ?visit .
  OPTIONAL { ?patient ns1:patientId ?patientId . }

  ?visit ns1:hasAdvice ?advice .
  ?advice ns1:hasAdviceItem ?procAdvice .

  ?procAdvice a ns1:ProcedureAdvice ;
              ns1:procedure_name ?procedure_name ;
              ns1:procedure_completion_date ?procedure_completion_date .

  OPTIONAL { ?procAdvice ns1:procedure_type ?procedure_type . }

  FILTER(
    REGEX(LCASE(STR(?procedure_name)), "inj") ||
    (BOUND(?procedure_type) && REGEX(LCASE(STR(?procedure_type)), "inj"))
  )

  FILTER(STRLEN(STR(?procedure_completion_date)) > 0)
}
GROUP BY ?patient ?patientId ?procedure_name
HAVING (COUNT(DISTINCT ?procedure_completion_date) > 1)
ORDER BY ?patient ?procedure_name
```

**NL:** Find the distribution of diagnoses in the database (number of distinct patients per diagnosis)

```sparql
PREFIX ns1: <http://clinical-example.org/ontology/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?diagnosisName (COUNT(DISTINCT ?patient) AS ?patientCount)
WHERE {
  ?patient rdf:type ns1:Patient ;
           ns1:hasVisit ?visit .

  ?visit ns1:hasDiagnosis ?diag .
  ?diag rdf:type ns1:Diagnosis ;
        ns1:diagnosisName ?diagnosisName .
}
GROUP BY ?diagnosisName
ORDER BY DESC(?patientCount) ?diagnosisName
```

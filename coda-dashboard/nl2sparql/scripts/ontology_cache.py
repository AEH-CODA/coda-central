"""
Ontology caching and smart column selection utilities.
This module intelligently maps natural language patterns to optimal SPARQL attributes.
"""

from typing import Dict, List, Set
import logging

logger = logging.getLogger(__name__)

# Smart column selection rules based on query intent
QUERY_PATTERNS = {
    "symptoms|complaints|complains|feeling": {
        "primary_class": "Complaint",
        "attributes": ["complaintName", "duration"],
        "relationships": ["hasComplaint"]
    },
    "blood pressure|bp|vital": {
        "primary_class": "VitalDetails",
        "attributes": ["systolicBP", "diastolicBP"],
        "relationships": ["hasVitals"],
        "ignore": ["otherVitals"]  # Ignore less relevant fields
    },
    "vision|sight|eye|visual": {
        "primary_class": "VisionDetails",
        "attributes": ["visionType", "leftEyeValue", "rightEyeValue"],
        "relationships": ["hasVisionDetails", "hasVisionItem"],
        "ignore": ["chartType", "intermediateValues"]
    },
    "refraction|lens|power": {
        "primary_class": "RefractionDetails",
        "attributes": ["reSphere", "reCylinder", "reAxis", "leSphere", "leCylinder", "leAxis"],
        "relationships": ["hasRefraction", "hasRefractionItem"]
    },
    "exam|finding|anterior|segment": {
        "primary_class": "AnteriorSegmentExam",
        "attributes": ["partName", "findingValue"],
        "relationships": ["hasAsExam", "hasFinding"]
    },
    "history|systemic|condition": {
        "primary_class": "SystemicHistory",
        "attributes": ["conditionCode", "duration", "hasPrescription"],
        "relationships": ["hasSystemicHistory", "hasReportedHistory"]
    },
    "investigation|test|lab|result": {
        "primary_class": "Investigation",
        "attributes": ["investigationName", "resultNumeric", "resultUnit"],
        "relationships": ["hasInvestigation"],
        "ignore": ["laterality"]  # Only use if specifically mentioned
    },
}

# Semantic alternatives (to reduce redundant columns)
SEMANTIC_ALTERNATIVES = {
    "systolicBP": ["BP_systolic", "sys_bp"],
    "visionType": ["vision_classification", "sight_type"],
    "resultNumeric": ["numeric_result", "test_value"],
}

def analyze_query_intent(nl_query: str) -> Dict:
    """Analyze natural language query to determine optimal attributes to select"""
    nl_query_lower = nl_query.lower()
    
    matched_patterns = {}
    for pattern, config in QUERY_PATTERNS.items():
        for keyword in pattern.split("|"):
            if keyword in nl_query_lower:
                matched_patterns[pattern] = config
                break
    
    logger.info(f"Query intent analysis: Found {len(matched_patterns)} matching patterns")
    
    return {
        "matched_patterns": matched_patterns,
        "should_ignore_columns": _extract_ignore_list(matched_patterns)
    }

def _extract_ignore_list(matched_patterns: Dict) -> Set[str]:
    """Extract list of columns to ignore based on matched patterns"""
    ignore_list = set()
    
    for config in matched_patterns.values():
        if "ignore" in config:
            ignore_list.update(config["ignore"])
    
    return ignore_list

def get_primary_classes(nl_query: str) -> List[str]:
    """Get the primary classes needed for the query"""
    analysis = analyze_query_intent(nl_query)
    
    primary_classes = []
    for config in analysis["matched_patterns"].values():
        if "primary_class" in config:
            primary_classes.append(config["primary_class"])
    
    # Always include Patient as base
    if "patient" in nl_query.lower():
        primary_classes.insert(0, "Patient")
    
    return list(set(primary_classes)) or ["Patient"]  # Default to Patient

def should_use_attribute(attribute: str, nl_query: str) -> bool:
    """Determine if an attribute should be included based on query context"""
    nl_query_lower = nl_query.lower()
    
    # Check if there are explicit alternatives mentioned
    for primary_attr, alternatives in SEMANTIC_ALTERNATIVES.items():
        if primary_attr == attribute:
            # Check if any alternative is better suited
            for alt in alternatives:
                if alt.replace("_", " ").lower() in nl_query_lower:
                    return False  # Skip if better alternative exists
    
    return True

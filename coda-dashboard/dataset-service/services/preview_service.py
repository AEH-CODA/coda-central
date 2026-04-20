import logging
import re
import httpx
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from config import GRAPHDB_ENDPOINT, SPARQL_QUERY_TIMEOUT, PREVIEW_ROW_LIMIT

logger = logging.getLogger(__name__)


class PreviewService:
    """Service for generating dataset previews from SPARQL queries."""
    
    @staticmethod
    def execute_sparql_query(query: str, timeout: int = SPARQL_QUERY_TIMEOUT) -> Dict[str, Any]:
        """
        Execute a SPARQL query on GraphDB and return results.
        
        Automatically adds LIMIT clause if not present.
        
        Args:
            query: SPARQL query string
            timeout: Query timeout in seconds
            
        Returns:
            Dict with query results from GraphDB
            
        Raises:
            ValueError: If query is invalid or empty
            TimeoutError: If query execution times out
            Exception: For other GraphDB errors
        """
        if not query or not query.strip():
            raise ValueError("SPARQL query cannot be empty")
        
        # Check if LIMIT is already present in the query
        query_upper = query.upper()
        if "LIMIT" not in query_upper:
            # Add LIMIT clause at the end
            query = f"{query.strip()} LIMIT {PREVIEW_ROW_LIMIT}"
        
        try:
            # GraphDB SPARQL endpoint expects JSON results via POST
            headers = {"Accept": "application/sparql-results+json"}
            
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    GRAPHDB_ENDPOINT,
                    headers=headers,
                    data={"query": query}
                )
                response.raise_for_status()
                
            results = response.json()
            logger.info(f"SPARQL query executed successfully. Rows: {len(results.get('results', {}).get('bindings', []))}")
            return results
            
        except httpx.TimeoutException as e:
            logger.error(f"SPARQL query timeout after {timeout}s: {str(e)}")
            raise TimeoutError(f"Query execution exceeded {timeout} seconds")
        except httpx.HTTPStatusError as e:
            logger.error(f"GraphDB returned error: {response.status_code} - {response.text}")
            raise ValueError("Invalid SPARQL query or GraphDB error")
        except Exception as e:
            logger.error(f"Error executing SPARQL query: {str(e)}")
            raise Exception("Failed to execute SPARQL query")
    
    @staticmethod
    def _is_aggregate_query(sparql_query: str) -> bool:
        """
        Detect if a SPARQL query is an aggregate query.
        
        Aggregate queries use functions like COUNT, SUM, AVG, MIN, MAX, GROUP_CONCAT
        or GROUP BY / HAVING clauses.
        
        Args:
            sparql_query: SPARQL query string
            
        Returns:
            True if query appears to be an aggregate query, False otherwise
        """
        query_upper = sparql_query.upper()
        
        # Check for aggregate functions
        aggregate_functions = ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'GROUP_CONCAT', 'SAMPLE']
        for func in aggregate_functions:
            if f'{func}(' in query_upper:
                return True
        
        # Check for GROUP BY or HAVING clauses
        if 'GROUP BY' in query_upper or 'HAVING' in query_upper:
            return True
        
        return False
    
    @staticmethod
    def _convert_results_to_dataframe(sparql_results: Dict[str, Any]) -> pd.DataFrame:
        """
        Convert GraphDB SPARQL JSON results to a pandas DataFrame.
        
        Handles the standard SPARQL JSON results format:
        {
          "head": {"vars": ["var1", "var2", ...]},
          "results": {"bindings": [{"var1": {...}, "var2": {...}}, ...]}
        }
        
        Args:
            sparql_results: Results from GraphDB SPARQL endpoint
            
        Returns:
            Pandas DataFrame with flattened results
        """
        # Extract bindings from SPARQL results
        bindings = sparql_results.get("results", {}).get("bindings", [])
        
        if not bindings:
            return pd.DataFrame()
        
        # Flatten the results - each binding has structure like:
        # {"var1": {"type": "...", "value": "..."}, "var2": {...}}
        rows = []
        for binding in bindings:
            row = {}
            for key, value_obj in binding.items():
                # Extract the actual value from the SPARQL result object
                if isinstance(value_obj, dict) and "value" in value_obj:
                    row[key] = value_obj["value"]
                else:
                    row[key] = value_obj
            rows.append(row)
        
        df = pd.DataFrame(rows)
        return df
    
    @staticmethod
    def _detect_column_type(series: pd.Series) -> str:
        """
        Detect the data type of a column.
        
        Returns one of: "numeric", "categorical", "datetime"
        """
        if series.empty or series.isna().all():
            return "categorical"  # Default for empty
        
        # Remove NaN for type detection
        non_null = series.dropna()
        
        if len(non_null) == 0:
            return "categorical"
        
        # Try to detect numeric
        try:
            pd.to_numeric(non_null)
            return "numeric"
        except (ValueError, TypeError):
            pass
        
        # Try to detect datetime
        try:
            pd.to_datetime(non_null)
            return "datetime"
        except (ValueError, TypeError):
            pass
        
        # Default to categorical (string-like)
        return "categorical"
    
    @staticmethod
    def _get_all_patient_id_columns(df: pd.DataFrame) -> set:
        """
        Detect all patient ID columns in the DataFrame.
        
        Looks for common column name patterns (case-insensitive):
        - patientid, patientId, patientID, PatientID
        - patient_id, patient-id
        - patient
        - p_id, pid
        
        Args:
            df: Pandas DataFrame
            
        Returns:
            Set of column names that are patient identifiers
        """
        patient_id_columns = set()
        
        for col in df.columns:
            col_lower = col.lower()
            
            # Direct exact matches (all lowercased for comparison)
            if col_lower in ['patientid', 'patient_id', 'patient', 'p_id', 'pid']:
                patient_id_columns.add(col)
                continue
            
            # Regex patterns to catch variations:
            # - matches 'patientid', 'patient id', 'patient_id', 'patient-id' (any case)
            if re.match(r'^patient[_\s\-]?id$', col_lower):
                patient_id_columns.add(col)
        
        return patient_id_columns
    
    @staticmethod
    def _detect_patient_id_column(df: pd.DataFrame) -> Optional[str]:
        """
        Detect if a patient ID column exists in the DataFrame.
        
        Returns the first detected patient ID column for patient insights computation.
        
        Args:
            df: Pandas DataFrame
            
        Returns:
            Column name if detected, None otherwise
        """
        patient_columns = PreviewService._get_all_patient_id_columns(df)
        return next(iter(patient_columns)) if patient_columns else None
    
    @staticmethod
    def _compute_patient_insights(df: pd.DataFrame, patient_col: str) -> Optional[Dict[str, Any]]:
        """
        Compute patient-level insights for datasets with a patient identifier.
        
        Args:
            df: Pandas DataFrame
            patient_col: Name of the patient ID column
            
        Returns:
            Dict with unique_patients, returning_patients counts, and appearance distribution, or None
        """
        if patient_col not in df.columns:
            return None
        
        try:
            # Count unique patients
            unique_patients = df[patient_col].nunique()
            
            # Count patient appearances (how many times each patient appears)
            patient_counts = df[patient_col].value_counts().sort_index()
            
            # Count returning patients (those with more than one record)
            returning_patients = (patient_counts > 1).sum()
            
            # Compute appearance distribution: how many patients have 1 visit, 2 visits, 3 visits, etc.
            appearance_histogram = patient_counts.value_counts().sort_index()
            appearance_distribution = {
                "labels": [str(int(visits)) for visits in appearance_histogram.index],
                "counts": [int(count) for count in appearance_histogram.values]
            }
            
            return {
                "patient_id_column": patient_col,
                "unique_patients": int(unique_patients),
                "returning_patients": int(returning_patients),
                "return_rate_percentage": float((returning_patients / unique_patients * 100) if unique_patients > 0 else 0),
                "appearance_distribution": appearance_distribution
            }
        except Exception as e:
            logger.warning(f"Failed to compute patient insights: {str(e)}")
            return None
    
    @staticmethod
    def _compute_numeric_stats(series: pd.Series) -> Dict[str, Any]:
        """Compute statistics for a numeric column."""
        numeric_series = pd.to_numeric(series, errors="coerce")
        return {
            "mean": float(numeric_series.mean()),
            "min": float(numeric_series.min()),
            "max": float(numeric_series.max()),
            "std": float(numeric_series.std()),
        }
    
    @staticmethod
    def _compute_categorical_stats(series: pd.Series) -> Dict[str, Any]:
        """Compute statistics for a categorical column."""
        value_counts = series.value_counts()
        top_5 = value_counts.head(5)
        top_values = {str(k): int(v) for k, v in top_5.items()}
        
        # Generate distribution data for all categories (for charting)
        all_categories = value_counts.to_dict()
        distribution = {
            "categories": [str(k) for k in all_categories.keys()],
            "counts": [int(v) for v in all_categories.values()]
        }
        
        return {
            "unique_values": int(series.nunique()),
            "top_values": top_values,
            "distribution": distribution,
        }
    
    @staticmethod
    def _compute_numeric_distribution(series: pd.Series, bins: int = 10) -> Dict[str, Any]:
        """
        Generate histogram distribution data with clean integer bin ranges.
        
        Uses integer-based binning to produce human-readable ranges like:
        - 18-19, 19-20, 20-21 (instead of 18.00-19.23)
        - Automatically adjusts bin width for nice ranges
        
        Args:
            series: Numeric series
            bins: Target number of bins
            
        Returns:
            Dict with clean bin labels and counts
        """
        numeric_series = pd.to_numeric(series, errors="coerce").dropna()
        
        if len(numeric_series) == 0:
            return {"bins": [], "counts": []}
        
        # Get min/max values
        min_val = numeric_series.min()
        max_val = numeric_series.max()
        
        # Handle edge case where all values are the same
        if min_val == max_val:
            return {"bins": [f"{int(min_val)}"], "counts": [len(numeric_series)]}
        
        # Calculate nice bin width
        data_range = max_val - min_val
        
        # Find a nice bin width (1, 2, 5, 10, 20, 50, 100, etc.)
        raw_bin_width = data_range / bins
        magnitude = 10 ** np.floor(np.log10(raw_bin_width))
        normalized_width = raw_bin_width / magnitude
        
        if normalized_width <= 1:
            nice_width = 1 * magnitude
        elif normalized_width <= 2:
            nice_width = 2 * magnitude
        elif normalized_width <= 5:
            nice_width = 5 * magnitude
        else:
            nice_width = 10 * magnitude
        
        # Create bins with nice boundaries (aligned to the nice width)
        bin_start = np.floor(min_val / nice_width) * nice_width
        bin_end = np.ceil(max_val / nice_width) * nice_width
        bin_edges = np.arange(bin_start, bin_end + nice_width, nice_width)
        
        # Create histogram
        counts, _ = np.histogram(numeric_series, bins=bin_edges)
        
        # Create clean bin labels (integers if possible)
        bin_labels = []
        for i in range(len(bin_edges) - 1):
            start = bin_edges[i]
            end = bin_edges[i + 1]
            
            # Format as integers if they are whole numbers
            if start == int(start) and end == int(end):
                bin_labels.append(f"{int(start)}-{int(end)}")
            else:
                # Round to 1 decimal place for non-integer ranges
                bin_labels.append(f"{start:.1f}-{end:.1f}")
        
        return {
            "bins": bin_labels,
            "counts": counts.tolist()
        }
    
    @staticmethod
    def _compute_datetime_stats(series: pd.Series) -> Dict[str, Any]:
        """Compute statistics for a datetime column."""
        datetime_series = pd.to_datetime(series, errors="coerce")
        min_date = datetime_series.min()
        max_date = datetime_series.max()
        
        return {
            "min_date": min_date.strftime("%Y-%m-%d") if pd.notna(min_date) else None,
            "max_date": max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else None,
        }
    
    @staticmethod
    def _compute_aggregate_numeric_stats(series: pd.Series) -> Dict[str, Any]:
        """
        Compute statistics for numeric column in aggregate results.
        
        Filters out NaN/Inf values which are not JSON-serializable.
        Single-value series will have NaN for std, which is replaced with None.
        
        Args:
            series: Pandas Series with numeric values
            
        Returns:
            Dict with mean, min, max, std (or None for invalid values)
        """
        numeric_series = pd.to_numeric(series, errors="coerce")
        
        stats = {}
        
        # Compute mean
        mean_val = numeric_series.mean()
        stats["mean"] = float(mean_val) if pd.notna(mean_val) and np.isfinite(mean_val) else None
        
        # Compute min
        min_val = numeric_series.min()
        stats["min"] = float(min_val) if pd.notna(min_val) and np.isfinite(min_val) else None
        
        # Compute max
        max_val = numeric_series.max()
        stats["max"] = float(max_val) if pd.notna(max_val) and np.isfinite(max_val) else None
        
        # Compute std (may be NaN for single-value series)
        std_val = numeric_series.std()
        stats["std"] = float(std_val) if pd.notna(std_val) and np.isfinite(std_val) else None
        
        return stats
    
    @staticmethod
    def _compute_aggregate_metadata(sparql_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute simplified metadata for aggregate query results.
        
        Aggregate queries return summary data (e.g., COUNT, SUM) rather than detail rows.
        This method returns basic metadata without attempting to compute distributions.
        
        Args:
            sparql_results: Results from GraphDB SPARQL endpoint
            
        Returns:
            Dict with dataset_summary, columns metadata (no distributions), and sample_rows
        """
        df = PreviewService._convert_results_to_dataframe(sparql_results)
        
        if df.empty:
            return {
                "dataset_summary": {"row_count": 0, "column_count": 0},
                "patient_insights": None,
                "columns": [],
                "sample_rows": [],
            }
        
        row_count = len(df)
        column_count = len(df.columns)
        
        # For aggregate queries, return simplified column metadata (no distributions)
        columns_metadata = []
        for col_name in df.columns:
            series = df[col_name]
            dtype = PreviewService._detect_column_type(series)
            
            col_meta = {
                "name": col_name,
                "dtype": dtype,
                "is_patient_id": False,  # Aggregate results don't have patient IDs
                "missing_percentage": 0.0,
                "unique_values": int(series.nunique()),
            }
            
            # Add basic stats but no distributions for aggregate results
            if dtype == "numeric":
                # Use special stats computation that filters out NaN/Inf
                col_meta.update(PreviewService._compute_aggregate_numeric_stats(series))
            elif dtype == "categorical":
                col_meta["unique_values"] = int(series.nunique())
            
            columns_metadata.append(col_meta)
        
        # Sample rows
        sample_rows = (
            df.head(5)
            .astype(object)
            .where(pd.notna(df.head(5)), None)
            .to_dict(orient="records")
        )
        
        logger.info(f"Aggregate query metadata computed: {row_count} rows, {column_count} columns")
        
        return {
            "dataset_summary": {
                "row_count": row_count,
                "column_count": column_count,
            },
            "patient_insights": None,
            "columns": columns_metadata,
            "sample_rows": sample_rows,
        }
    
    @staticmethod
    def compute_metadata(sparql_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute dataset metadata from SPARQL results with enhanced Kaggle-style insights.
        
        Args:
            sparql_results: Results from GraphDB SPARQL endpoint
            
        Returns:
            Dict with dataset_summary, patient_insights (if applicable), columns metadata, and sample_rows
        """
        # Convert to DataFrame
        df = PreviewService._convert_results_to_dataframe(sparql_results)
        
        if df.empty:
            return {
                "dataset_summary": {"row_count": 0, "column_count": 0},
                "patient_insights": None,
                "columns": [],
                "sample_rows": [],
            }
        
        # Dataset-level metadata
        row_count = len(df)
        column_count = len(df.columns)
        
        # Detect all patient ID columns
        patient_id_columns = PreviewService._get_all_patient_id_columns(df)
        
        # Compute patient insights using the first patient ID column (if exists)
        patient_insights = None
        if patient_id_columns:
            patient_id_col = next(iter(patient_id_columns))
            patient_insights = PreviewService._compute_patient_insights(df, patient_id_col)
        
        # Column-level metadata
        columns_metadata = []
        for col_name in df.columns:
            series = df[col_name]
            
            # Check if this is a patient ID column
            is_patient_id = col_name in patient_id_columns
            
            col_meta = {
                "name": col_name,
                "dtype": "identifier" if is_patient_id else PreviewService._detect_column_type(series),
                "is_patient_id": is_patient_id,
                "missing_percentage": 0.0,  # Patient ID should not have nulls
                "unique_values": int(series.nunique()),
            }
            
            # Skip distribution stats for patient ID columns
            if is_patient_id:
                # Only include basic info for patient ID columns
                logger.debug(f"Skipping distribution stats for patient ID column: {col_name}")
            else:
                # Compute missing percentage for non-ID columns
                missing_count = series.isna().sum()
                col_meta["missing_percentage"] = float((missing_count / len(series)) * 100) if len(series) > 0 else 0.0
                
                dtype = col_meta["dtype"]
                
                if dtype == "numeric":
                    col_meta.update(PreviewService._compute_numeric_stats(series))
                    col_meta["distribution"] = PreviewService._compute_numeric_distribution(series)
                elif dtype == "categorical":
                    col_meta.update(PreviewService._compute_categorical_stats(series))
                elif dtype == "datetime":
                    col_meta.update(PreviewService._compute_datetime_stats(series))
            
            columns_metadata.append(col_meta)
        
        # Sample rows (first 5)
        sample_rows = (
            df.head(5)
            .astype(object)
            .where(pd.notna(df.head(5)), None)
            .to_dict(orient="records")
        )
        
        return {
            "dataset_summary": {
                "row_count": row_count,
                "column_count": column_count,
            },
            "patient_insights": patient_insights,
            "columns": columns_metadata,
            "sample_rows": sample_rows,
        }
    
    @staticmethod
    def generate_preview(sparql_query: str, timeout: int = SPARQL_QUERY_TIMEOUT) -> Dict[str, Any]:
        """
        Generate a complete preview for a SPARQL query.
        
        Orchestrates query execution and metadata computation.
        Automatically detects aggregate queries and handles them appropriately.
        
        Args:
            sparql_query: SPARQL query string
            timeout: Query timeout in seconds
            
        Returns:
            Dict with preview metadata (dataset_summary, columns, sample_rows)
            
        Raises:
            ValueError: For invalid queries
            TimeoutError: For timeout
            Exception: For other errors
        """
        try:
            # Check if this is an aggregate query
            is_aggregate = PreviewService._is_aggregate_query(sparql_query)
            logger.debug(f"Query is aggregate: {is_aggregate}")
            
            # Execute query
            results = PreviewService.execute_sparql_query(sparql_query, timeout)
            
            # Compute metadata based on query type
            if is_aggregate:
                metadata = PreviewService._compute_aggregate_metadata(results)
            else:
                metadata = PreviewService.compute_metadata(results)
            
            logger.info(f"Preview generated: {metadata['dataset_summary']['row_count']} rows, "
                       f"{metadata['dataset_summary']['column_count']} columns")
            
            return metadata
            
        except (ValueError, TimeoutError) as e:
            logger.warning(f"Preview generation failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in preview generation: {str(e)}")
            raise Exception("Failed to generate preview")

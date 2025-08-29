
import os
import pydicom
from pathlib import Path

def run(*args, **kwargs):
    dicom_dir = Path("/mnt/input/dicom_data")

    debug_info = {
        "scanned_path": str(dicom_dir),
        "all_files_found": [],
        "files_read_success": 0,
        "files_read_failed": 0
    }

    if not dicom_dir.exists():
        return {
            "error": f"DICOM directory not found: {dicom_dir}",
            "debug": debug_info
        }

    selected_tags = [
        "SOPClassUID",
        "SeriesInstanceUID",
        "PatientID",
        "Modality",
        "AccessionNumber",
        "ManufacturerModelName",
        "ImageLaterality"
    ]

    query_field = kwargs.get("query_field")
    query_value = kwargs.get("query_value")

    dicom_data_list = []

    for root, dirs, files in os.walk(dicom_dir):
        scan_number = os.path.basename(root)
        for file in files:
            if file.lower().endswith(".dcm"):
                dicom_path = os.path.join(root, file)
                debug_info["all_files_found"].append(str(dicom_path))
                try:
                    dicom_data = pydicom.dcmread(dicom_path)
                    debug_info["files_read_success"] += 1
                    image_name = os.path.basename(dicom_path)

                    if query_field and query_value:
                        attr_val = getattr(dicom_data, query_field, None)
                        if str(attr_val).strip() != str(query_value).strip():
                            continue

                    dicom_dict = {
                        "Patient Scan Number": scan_number,
                        "Image Name": image_name
                    }
                    for tag in selected_tags:
                        dicom_dict[tag] = getattr(dicom_data, tag, "Not Found")
                    dicom_data_list.append(dicom_dict)
                except Exception as e:
                    debug_info["files_read_failed"] += 1
                    continue

    return {
        "query": f"{query_field} = {query_value}" if query_field else "No filter",
        "matches_found": len(dicom_data_list),
        "dicom_metadata": dicom_data_list,
        "debug": debug_info
    }

import io
import json
import logging
import zipfile

logger = logging.getLogger(__name__)

# ZIP bomb protection limits
MAX_ZIP_MEMBERS = 1000
MAX_ZIP_MEMBER_SIZE = 512 * 1024 * 1024
MAX_ZIP_TOTAL_SIZE = 1 * 1024 * 1024 * 1024
MAX_ZIP_RATIO = 100


def safe_open_zip(file):
    """Open a zip file after validating its uncompressed resource requirements."""
    zip_file = zipfile.ZipFile(file.name, "r") if isinstance(file, io.TextIOWrapper) else zipfile.ZipFile(file, "r")
    try:
        members = zip_file.infolist()
        if len(members) > MAX_ZIP_MEMBERS:
            msg = f"Zip file contains {len(members)} members, exceeding the limit of {MAX_ZIP_MEMBERS}."
            raise ValueError(msg)

        total_size = 0
        for member in members:
            if member.file_size > MAX_ZIP_MEMBER_SIZE:
                msg = (
                    f"Zip member '{member.filename}' has uncompressed size {member.file_size} bytes, "
                    f"exceeding the per-member limit of {MAX_ZIP_MEMBER_SIZE} bytes."
                )
                raise ValueError(msg)
            if member.compress_size > 0 and member.file_size / member.compress_size > MAX_ZIP_RATIO:
                ratio = member.file_size / member.compress_size
                msg = (
                    f"Zip member '{member.filename}' has a compression ratio of "
                    f"{ratio:.1f}:1, exceeding the limit of {MAX_ZIP_RATIO}:1."
                )
                raise ValueError(msg)

            total_size += member.file_size
            if total_size > MAX_ZIP_TOTAL_SIZE:
                msg = f"Zip file total uncompressed size exceeds the limit of {MAX_ZIP_TOTAL_SIZE} bytes."
                raise ValueError(msg)
    except Exception:
        zip_file.close()
        raise

    return zip_file


def safe_read_all_zip(file):
    """Read all zip members into a dictionary after validating resource limits."""
    zip_file = safe_open_zip(file)
    try:
        return {name: zip_file.read(name) for name in zip_file.namelist()}
    finally:
        zip_file.close()


def get_npm_cwe(item_node):
    """
    Possible values:
        "cwe": null
        "cwe": ["CWE-173", "CWE-200","CWE-601"]  (or [])
        "cwe": "CWE-1234"
        "cwe": '["CWE-173","CWE-200","CWE-601"]' (or "[]")
    """
    cwe_node = item_node.get("cwe")
    if cwe_node:
        if isinstance(cwe_node, list):
            return int(cwe_node[0][4:])
        if cwe_node.startswith("CWE-"):
            cwe_string = cwe_node[4:]
            if cwe_string:
                return int(cwe_string)
        elif cwe_node.startswith("["):
            cwe = json.loads(cwe_node)
            if cwe:
                return int(cwe[0][4:])

    # Use CWE-1035 as fallback (vulnerable third party component)
    return 1035

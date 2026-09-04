from bs4 import BeautifulSoup
from datetime import datetime
import logging
from dojo.utils import extract_field_from_text_regex
logger = logging.getLogger(__name__)


def get_url_presigned(session,
                      key,
                      bucket,
                      expires_in=3600):
    url = session.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expires_in
    )
    logger.debug(f"REPORT FINDING: {url}")
    return url

def extract_field_from_text_html(text, field_name):
    text_value = ""
    soup = BeautifulSoup(text, "html.parser")
    text_found = soup.find("strong", string=field_name)
    if text_found:
        text_value = text_found.next_sibling.strip()
    return text_value

def upload_s3(session_s3, buffer, bucket, key):
    try:
        response = session_s3.put_object(Bucket=bucket, Key=key, Body=buffer)
        logger.info(f"REPORT FINDING: Upload successful: {response}")
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            return response
        else:
            logger.error(f"REPORT FINDING: Upload failed with status code: {response['ResponseMetadata']['HTTPStatusCode']}")
            raise Exception(response["ResponseMetadata"]["HTTPStatusCode"], "Failed to upload to S3")
    except Exception as e:
        logger.error(f"REPORT FINDING: Error uploading to S3: {e}")
        raise Exception("Failed to upload to S3 after multiple attempts due to expired token.")

# desired report column order; anything not listed here keeps its current
# relative order and is appended after these
REPORT_COLUMN_ORDER = [
    "id", "title", "description", "component_name", "component_version", "mitigation",
    "vulnerability_ids", "references", "priority_classification", "priority", "cvssv3_score",
    "created", "sla_start_date", "sla_expiration_date", "sla_age", "sla_days_remaining", "active", "false_p", "is_mitigated", "mitigated",
    "risk_status", "accepted_by", "risk_acceptance_expiration_date", "long_term_acceptance", "product_type_environment", "product_type",
    "product", "engagement", "area_responsible", "company", "reporter", "reporter_name", "tags", "custom_id",
    "environment_device", "account_id_device",
    "environment_image", "cluster", "registry_image", "repository_image", "namespace_image", "tag_image",
    "cloud_id", "item_class", "class_id", "environment_device", "account_id_device"
]


def get_column_order(names):
    """Index permutation putting REPORT_COLUMN_ORDER columns first (in that order),
    then any remaining columns in their original relative order."""
    priority = {name: i for i, name in enumerate(REPORT_COLUMN_ORDER)}
    return sorted(range(len(names)), key=lambda i: priority.get(names[i], len(REPORT_COLUMN_ORDER)))

def get_generic_field_keys(finding, excludes_list, allowed_attributes):
    """
    The set of reportable attribute names is the same for every finding of the same
    model, so callers should compute this once (from the header row) and reuse the
    returned list for every subsequent data row instead of re-walking dir(finding).
    """
    keys = []
    for key in dir(finding):
        # excludes_list/underscore check must run before getattr() so known-bad
        # accessors (e.g. github_issue/jira_issue reverse o2o, objects manager)
        # are never touched, matching the original short-circuited condition.
        if key in excludes_list or key.startswith("_"):
            continue
        try:
            is_callable = callable(getattr(finding, key))
            if not is_callable or key in allowed_attributes:
                if is_callable and key not in allowed_attributes:
                    continue
                keys.append(key)
        except Exception as exc:
            logger.warning(f"Error in attribute: {key}" + str(exc))
            keys.append(key)
            continue
    return keys

def configure_headers_excel(finding, worksheet, font_bold, excludes_list, allowed_attributes, row_num, col_num):
    generic_fields = get_generic_field_keys(finding, excludes_list, allowed_attributes)
    raw_fields = list(generic_fields)
    raw_fields.extend((
        "risk_acceptance_expiration_date",
        "environment_image",
        "cluster",
        "registry_image",
        "repository_image",
        "namespace_image",
        "tag_image",
        "cloud_id",
        "custom_id",
        "engagement",
        "area_responsible",
        "product",
        "product_type",
        "product_type_environment",
        "company",
        "vulnerability_ids",
        "tags",
        "reporter_name",
        "environment_device",
        "account_id_device",
        "classification",
    ))
    order = get_column_order(raw_fields)
    for i in order:
        cell = worksheet.cell(row=row_num, column=col_num, value=raw_fields[i])
        cell.font = font_bold
        col_num += 1
    return generic_fields, order

def configure_values_excel(finding, worksheet, excludes_list, allowed_foreign_keys, allowed_attributes, row_num, col_num, EXCEL_CHAR_LIMIT, generic_fields=None, order=None):
    if generic_fields is None:
        generic_fields = get_generic_field_keys(finding, excludes_list, allowed_attributes)
    raw_values = []
    for key in generic_fields:
        try:
            attr_value = getattr(finding, key)
            is_callable = callable(attr_value)
            value = finding.__dict__.get(key) if not is_callable else None
            if (key in allowed_foreign_keys or key in allowed_attributes) and attr_value:
                value = attr_value() if is_callable else str(attr_value)
            if value and isinstance(value, datetime):
                value = value.replace(tzinfo=None)
            raw_values.append(value)
        except Exception as exc:
            logger.warning(f"Error in attribute: {key}" + str(exc))
            raw_values.append("Value not supported")
            continue
    value_ra_expiration_date = finding.risk_acceptance.expiration_date.strftime("%Y-%m-%d") if finding.risk_acceptance else ""
    raw_values.append(value_ra_expiration_date)
    raw_values.append(extract_field_from_text_regex(finding.impact, "Environment"))
    raw_values.append(extract_field_from_text_html(finding.description, "Cluster:"))
    raw_values.append(extract_field_from_text_regex(finding.impact, "Registry"))
    raw_values.append(extract_field_from_text_regex(finding.impact, "Repository"))
    raw_values.append(extract_field_from_text_html(finding.description, "Namespaces:"))
    raw_values.append(extract_field_from_text_html(finding.description, "Tag:"))
    raw_values.append(extract_field_from_text_html(finding.description, "Cloud Id:"))
    raw_values.append(extract_field_from_text_html(finding.description, "Custom Id:"))
    raw_values.append(finding.test.engagement.name)
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.product.description, "AREA RESPONSABLE TI"))
    raw_values.append(finding.test.engagement.product.name)
    raw_values.append(finding.test.engagement.product.prod_type.name)
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.product.prod_type.description, "Environment"))
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.product.description, "COMPANY"))

    vulnerability_ids_value = ""
    for num_vulnerability_ids, vulnerability_id in enumerate(finding.vulnerability_ids):
        if num_vulnerability_ids > 5:
            vulnerability_ids_value += "..."
            break
        vulnerability_ids_value += f"{vulnerability_id}; \n"
    if finding.cve and vulnerability_ids_value.find(finding.cve) < 0:
        vulnerability_ids_value += finding.cve
    vulnerability_ids_value = vulnerability_ids_value.removesuffix("; \n")
    raw_values.append(vulnerability_ids_value)
    # tags
    tags_value = ""
    for tag in finding.tags.all():
        tags_value += f"{tag}; \n"
    tags_value = tags_value.removesuffix("; \n")
    raw_values.append(tags_value)
    raw_values.append(finding.reporter.get_full_name() if finding.reporter else "")
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.description, "SYSTEM ENVIRONMENT"))
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.description, "ACCOUNT ID"))
    # classification
    if "tenable" in tags_value or "prisma" in tags_value:
        classification = extract_field_from_text_regex(finding.test.engagement.description, "ITEM")
    else:
        classification = extract_field_from_text_regex(finding.test.engagement.product.description, "ITEM")
    raw_values.append(classification)

    if order is None:
        order = range(len(raw_values))
    for i in order:
        worksheet.cell(row=row_num, column=col_num, value=raw_values[i])
        col_num += 1

def configure_headers_csv(finding, excludes_list, allowed_attributes, fields):
    generic_fields = get_generic_field_keys(finding, excludes_list, allowed_attributes)
    raw_fields = list(generic_fields)
    raw_fields.extend((
        "risk_acceptance_expiration_date",
        "environment_image",
        "cluster",
        "registry_image",
        "repository_image",
        "namespace_image",
        "tag_image",
        "cloud_id",
        "custom_id",
        "engagement",
        "area_responsible",
        "product",
        "product_type",
        "product_type_environment",
        "company",
        "vulnerability_ids",
        "tags",
        "reporter_name",
        "environment_device",
        "account_id_device",
        "item_class",
        "class_id"
    ))
    order = get_column_order(raw_fields)
    fields.extend(raw_fields[i] for i in order)
    return generic_fields, order

def configure_values_csv(finding, excludes_list, allowed_foreign_keys, allowed_attributes, fields, EXCEL_CHAR_LIMIT, generic_fields=None, order=None):
    if generic_fields is None:
        generic_fields = get_generic_field_keys(finding, excludes_list, allowed_attributes)
    raw_values = []
    for key in generic_fields:
        try:
            attr_value = getattr(finding, key)
            is_callable = callable(attr_value)
            value = finding.__dict__.get(key) if not is_callable else None
            if (key in allowed_foreign_keys or key in allowed_attributes) and attr_value:
                value = attr_value() if is_callable else str(attr_value)
            if value and isinstance(value, str):
                value = value.replace("\n", " NEWLINE ").replace("\r", "")
            raw_values.append(value)
        except Exception as exc:
            logger.error("Error in attribute: " + str(exc))
            raw_values.append("Value not supported")
            continue
    
    value_ra_expiration_date = finding.risk_acceptance.expiration_date.strftime("%Y-%m-%d") if finding.risk_acceptance else ""
    raw_values.append(value_ra_expiration_date)
    raw_values.append(extract_field_from_text_regex(finding.impact, "Environment"))
    raw_values.append(extract_field_from_text_html(finding.description, "Cluster:"))
    raw_values.append(extract_field_from_text_regex(finding.impact, "Registry"))
    raw_values.append(extract_field_from_text_regex(finding.impact, "Repository"))
    raw_values.append(extract_field_from_text_html(finding.description, "Namespaces:"))
    raw_values.append(extract_field_from_text_html(finding.description, "Tag:"))
    raw_values.append(extract_field_from_text_html(finding.description, "Cloud Id:"))
    raw_values.append(extract_field_from_text_html(finding.description, "Custom Id:"))
    raw_values.append(finding.test.engagement.name)
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.product.description, "AREA RESPONSABLE TI"))
    raw_values.append(finding.test.engagement.product.name)
    raw_values.append(finding.test.engagement.product.prod_type.name)
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.product.prod_type.description, "Environment"))
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.product.description, "COMPANY"))

    vulnerability_ids_value = ""
    for num_vulnerability_ids, vulnerability_id in enumerate(finding.vulnerability_ids):
        if num_vulnerability_ids > 5:
            vulnerability_ids_value += "..."
            break
        vulnerability_ids_value += f"{vulnerability_id}; "
    if finding.cve and vulnerability_ids_value.find(finding.cve) < 0:
        vulnerability_ids_value += finding.cve
    vulnerability_ids_value = vulnerability_ids_value.removesuffix("; ")
    raw_values.append(vulnerability_ids_value)
    # Tags
    tags_value = ""
    for num_tags, tag in enumerate(finding.tags.all()):
        if num_tags > 5:
            tags_value += "..."
            break
        tags_value += f"{tag}; "
    tags_value = tags_value.removesuffix("; ")
    raw_values.append(tags_value)
    raw_values.append(finding.reporter.get_full_name() if finding.reporter else "")
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.description, "SYSTEM ENVIRONMENT"))
    raw_values.append(extract_field_from_text_regex(finding.test.engagement.description, "ACCOUNT ID"))
    # Item Class
    classification = extract_field_from_text_regex(finding.test.engagement.description, "ITEM")
    if not classification:
        classification = extract_field_from_text_regex(finding.test.engagement.product.description, "ITEM")
    raw_values.append(classification)

    # Class ID
    class_id = extract_field_from_text_regex(finding.test.engagement.description, "CLASSID")
    if not class_id:
        class_id = extract_field_from_text_regex(finding.test.engagement.product.description, "CLASSID")
    raw_values.append(class_id)

    if order is None:
        order = range(len(raw_values))
    fields.extend(raw_values[i] for i in order)
import base64
import binascii
import logging
import os
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction

from dojo.authorization.roles_permissions import Permissions
from dojo.finding.queries import get_authorized_findings
from dojo.models import Engagement, Finding

logger = logging.getLogger(__name__)


class EngineLookupError(Exception):
    pass


def search_engine_base_url():
    core_engine = (settings.PROVIDER_CORE_ENGINE or "").strip()
    parsed_url = urlparse(core_engine)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("Configure DD_PROVIDER_CORE_ENGINE with the core engine base URL.")
    return core_engine.rstrip("/") + "/engine-backend/search"


class EngineImageClient:
    def __init__(self):
        self.base_url = search_engine_base_url()
        self.session = requests.Session()
        header_name = getattr(settings, "PROVIDER_CORE_ENGINE_SEARCH_HEADER_NAME",
                              os.getenv("DD_PROVIDER_CORE_ENGINE_SEARCH_HEADER_NAME", "x-api-key"))
        header_value = getattr(settings, "PROVIDER_CORE_ENGINE_SEARCH_HEADER_VALUE",
                               os.getenv("DD_PROVIDER_CORE_ENGINE_SEARCH_HEADER_VALUE", ""))
        if header_value:
            self.session.headers[header_name] = header_value

    def close(self):
        self.session.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self.base_url + "/" + path, timeout=(5, 60),
                                            allow_redirects=False, **kwargs)
            response.raise_for_status()
            if response.status_code != 200:
                raise EngineLookupError("Search Engine did not return HTTP 200.")
            payload = response.json()
            if not isinstance(payload, dict):
                raise EngineLookupError("Search Engine returned an invalid response.")
            return payload
        except (requests.RequestException, ValueError) as error:
            raise EngineLookupError("Search Engine request failed; no findings were changed.") from error

    def get_runtime(self, engagement_name):
        images = self.request("GET", "getImagesRuntime", params={"searchKey": "image", "searchValue": engagement_name}).get("images")
        if not isinstance(images, list) or any(not isinstance(image, str) or not image.strip() for image in images):
            raise EngineLookupError("Invalid images list from Search Engine.")
        return sorted(set(images))

    def get_deployments(self, images):
        deployments = {}
        for offset in range(0, len(images), 500):
            batch = images[offset:offset + 500]
            rows = self.request("POST", "getImageDeployments", json={"images": batch}).get("deployments")
            if not isinstance(rows, list):
                raise EngineLookupError("Invalid deployments list from Search Engine.")
            for row in rows:
                if not isinstance(row, dict) or row.get("image") not in batch:
                    raise EngineLookupError("Unexpected image in deployment response.")
                deployment, container = row.get("deployment") or "", row.get("containerName") or ""
                if not isinstance(deployment, str) or not isinstance(container, str):
                    raise EngineLookupError("Invalid deployment or container name.")
                deployments.setdefault(row["image"], []).append((deployment, container))
        return deployments


def description_fields(document):
    fields = {}
    for label in document.find_all("strong"):
        name = label.get_text(strip=True).rstrip(":")
        if label.parent.name == "p":
            fields[name] = "".join(str(sibling.get_text() if hasattr(sibling, "get_text") else sibling)
                                   for sibling in label.next_siblings).strip()
    return fields


def set_description_field(document, name, value):
    labels = [label for label in document.find_all("strong")
              if label.get_text(strip=True).casefold() == (name + ":").casefold()]
    if len(labels) > 1 or (labels and labels[0].parent.name != "p"):
        raise ValueError(f"Ambiguous {name} field in description.")
    paragraph = document.new_tag("p")
    label = document.new_tag("strong")
    label.string = name + ":"
    paragraph.append(label)
    paragraph.append(" " + value)
    if labels:
        labels[0].parent.replace_with(paragraph)
    else:
        document.append(paragraph)


def select_deployment_pairs(image, runtime_images, deployments_by_image):
    if image in runtime_images:
        return sorted(set(deployments_by_image.get(image, [])))
    repository = image.rsplit(":", 1)[0]
    candidates = [candidate for candidate in runtime_images if candidate.rsplit(":", 1)[0] == repository]
    if not candidates:
        return []
    pair_sets = {tuple(sorted(set(deployments_by_image.get(candidate, [])))) for candidate in candidates}
    if len(pair_sets) != 1:
        raise ValueError("Runtime tags have different deployments; cannot identify this finding's deployment.")
    return list(next(iter(pair_sets)))


def prepare_finding_identity(finding, runtime_images, deployments_by_image):
    document = BeautifulSoup(finding.description or "", "html.parser")
    fields = description_fields(document)
    impact = dict(line.partition(":")[::2] for line in (finding.impact or "").splitlines() if ":" in line)
    registry = impact.get("Registry", fields.get("Registry", "")).strip()
    repository = impact.get("Repository", fields.get("Repository", "")).strip()
    tag = fields.get("Tag", impact.get("Tag", "")).strip()
    cloud_id = fields.get("Cloud Id", impact.get("Image ID", "")).strip()
    if not registry or not repository:
        raise ValueError("Registry and Repository are required to reconstruct the identity.")
    if finding.unique_id_from_tool:
        try:
            decoded = base64.b64decode(finding.unique_id_from_tool, validate=True).decode("utf-8")
        except (ValueError, binascii.Error, UnicodeDecodeError) as error:
            raise ValueError("Current unique_id_from_tool is not a valid UTF-8 Base64 identity.") from error
    else:
        decoded = fields.get("Custom Id", "")
    prefix = registry + "/" + repository + "@"
    prefixes = [prefix + ",,"]
    if cloud_id:
        prefixes.append(prefix + cloud_id + ",")
    if "Deployment" in fields and "Container Name" in fields:
        deployment_names = fields["Deployment"].split(",") if fields["Deployment"] else []
        container_names = fields["Container Name"].split(",") if fields["Container Name"] else []
        if len(deployment_names) != len(container_names):
            raise ValueError("Deployment and Container Name fields have different lengths.")
        current_pairs = sorted(set(zip(deployment_names, container_names, strict=True)))
        pair_values = [value for pair in current_pairs for value in pair] or ["", ""]
        prefixes.append(prefix + ",".join(pair_values) + ",")
    matching_prefix = next((candidate for candidate in prefixes if decoded.startswith(candidate)), None)
    if matching_prefix is None:
        raise ValueError("Existing custom ID does not match the stored image metadata; migration skipped.")
    suffix = decoded[len(matching_prefix):]
    if suffix.count(",") < 5:
        raise ValueError("Existing custom ID does not contain all six vulnerability fields.")
    pairs = select_deployment_pairs(registry + "/" + repository + ":" + tag, runtime_images, deployments_by_image)
    pair_values = [value for pair in pairs for value in pair] or ["", ""]
    identity = prefix + ",".join(pair_values) + "," + suffix
    encoded = base64.b64encode(identity.encode("utf-8")).decode("ascii")
    if len(encoded) > 3000:
        raise ValueError("New unique_id_from_tool exceeds the 3000-character field limit.")
    set_description_field(document, "Custom Id", identity)
    set_description_field(document, "Deployment", ",".join(pair[0] for pair in pairs))
    set_description_field(document, "Container Name", ",".join(pair[1] for pair in pairs))
    return {"unique_id_from_tool": encoded, "description": str(document), "deployment_count": len(pairs)}


def migrate_engagement(engagement, queryset, client, dry_run):
    images = client.get_runtime(engagement.name)
    deployments = client.get_deployments(images)
    result = {"engagement_id": engagement.pk, "name": engagement.name, "runtime_images": len(images),
              "would_update": 0, "updated": 0, "unchanged": 0, "without_deployments": 0, "skipped": []}
    prepared = []
    for finding in queryset.filter(test__engagement_id=engagement.pk).iterator(chunk_size=500):
        try:
            values = prepare_finding_identity(finding, images, deployments)
        except ValueError as error:
            result["skipped"].append({"id": finding.pk, "reason": str(error)})
            continue
        if values["deployment_count"] == 0:
            result["without_deployments"] += 1
        if finding.unique_id_from_tool == values["unique_id_from_tool"] and finding.description == values["description"]:
            result["unchanged"] += 1
            continue
        prepared.append((finding.pk, finding.unique_id_from_tool, finding.description, values))
    result["would_update"] = len(prepared)
    if dry_run or not prepared:
        return result
    with transaction.atomic():
        eligible_ids = queryset.filter(pk__in=[entry[0] for entry in prepared]).values("pk")
        locked = {finding.pk: finding for finding in Finding.objects.filter(pk__in=eligible_ids)
                  .select_for_update(of=("self",)).order_by("pk")}
        changed = []
        for finding_id, old_id, old_description, values in prepared:
            finding = locked.get(finding_id)
            if finding is None or finding.unique_id_from_tool != old_id or finding.description != old_description:
                result["skipped"].append({"id": finding_id, "reason": "Finding changed during migration; retry."})
                continue
            finding.unique_id_from_tool = values["unique_id_from_tool"]
            finding.description = values["description"]
            changed.append(finding)
        if changed:
            Finding.objects.bulk_update(changed, ["unique_id_from_tool", "description"], batch_size=500)
        result["updated"] = len(changed)
    return result


def prisma_images_identity_findings(user):
    return get_authorized_findings(Permissions.Finding_Edit, user=user).filter(
        active=True, is_mitigated=False,
        test__title__iregex=r"^ciclo[ _-]escaneo$",
        test__engagement__description__iregex=r"(^|\n)\s*ITEM:\s*(IMAGES|ECR)(\s|$)",
    ).filter(tags__name="prisma").filter(tags__name="images")


def run_bulk_migration(user, dry_run, after_engagement_id=0, batch_size=10, engagement_ids=None):
    eligible = prisma_images_identity_findings(user)
    engagements = Engagement.objects.filter(pk__in=eligible.values("test__engagement_id"),
                                            pk__gt=after_engagement_id)
    if engagement_ids:
        engagements = engagements.filter(pk__in=engagement_ids)
    total = engagements.count()
    totals = {"processed": 0, "would_update": 0, "updated": 0, "unchanged": 0, "skipped": 0, "errors": 0}
    logger.info("Prisma images identity migration started user=%s dry_run=%s engagements=%s", user.pk, dry_run, total)
    if total == 0:
        return totals
    cursor = after_engagement_id
    client = EngineImageClient()
    try:
        while True:
            batch = list(engagements.filter(pk__gt=cursor).order_by("pk")[:batch_size])
            if not batch:
                break
            for engagement in batch:
                cursor = engagement.pk
                totals["processed"] += 1
                try:
                    result = migrate_engagement(engagement, eligible, client, dry_run)
                except EngineLookupError as error:
                    totals["errors"] += 1
                    logger.warning("Prisma images identity migration engagement_id=%s failed: %s", engagement.pk, error)
                    continue
                totals["would_update"] += result["would_update"]
                totals["updated"] += result["updated"]
                totals["unchanged"] += result["unchanged"]
                totals["skipped"] += len(result["skipped"])
                for skipped in result["skipped"]:
                    logger.debug("Prisma images identity migration finding_id=%s skipped: %s", skipped["id"], skipped["reason"])
                logger.info(
                    "Prisma images identity migration progress %s/%s engagement_id=%s runtime_images=%s "
                    "would_update=%s updated=%s unchanged=%s skipped=%s",
                    totals["processed"], total, engagement.pk, result["runtime_images"],
                    result["would_update"], result["updated"], result["unchanged"], len(result["skipped"]))
    finally:
        client.close()
    logger.info("Prisma images identity migration finished user=%s dry_run=%s totals=%s", user.pk, dry_run, totals)
    return totals

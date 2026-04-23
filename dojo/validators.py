import logging
import re
from collections.abc import Callable

import cvss
from cvss import CVSS2, CVSS3, CVSS4
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

logger = logging.getLogger(__name__)

TAG_PATTERN = re.compile(r'[ ,\'"]')  # Matches spaces, commas, single quotes, double quotes

# TTL (seconds) for cached tag PKs. Tags are rarely deleted; 1 h is a safe default.
_TAG_CACHE_TTL = 3600


def tag_validator(value: str | list[str], exception_class: Callable = ValidationError) -> None:
    error_messages = []

    if not value:
        return

    if isinstance(value, list):
        error_messages.extend(f"Invalid tag: '{tag}'. Tags should not contain spaces, commas, or quotes." for tag in value if TAG_PATTERN.search(tag))
    elif isinstance(value, str):
        if TAG_PATTERN.search(value):
            error_messages.append(f"Invalid tag: '{value}'. Tags should not contain spaces, commas, or quotes.")
    else:
        error_messages.append(f"Value must be a string or list of strings: {value} - {type(value)}.")

    if error_messages:
        logger.debug(f"Tag validation failed: {error_messages}")
        raise exception_class(error_messages)


def clean_tags(value: str | list[str], exception_class: Callable = ValidationError) -> str | list[str]:

    if not value:
        return value

    if isinstance(value, list):
        # Replace ALL occurrences of problematic characters in each tag
        return [TAG_PATTERN.sub("_", tag) for tag in value]

    if isinstance(value, str):
        # Replace ALL occurrences of problematic characters in the tag
        return TAG_PATTERN.sub("_", value)

    msg = f"Value must be a string or list of strings: {value} - {type(value)}."
    raise exception_class(msg)


def resolve_persisted_tags(tag_manager, value: str | list[str]) -> list:
    if not value:
        return []

    if isinstance(value, str):
        tag_names = [value]
    else:
        tag_names = value

    case_sensitive = tag_manager.tag_options.case_sensitive
    force_lowercase = tag_manager.tag_options.force_lowercase
    tag_model = tag_manager.tag_model
    model_label = tag_model._meta.label_lower
    resolved_tags = []
    seen_names = set()

    for raw_name in tag_names:
        tag_name = str(raw_name)
        if force_lowercase:
            tag_name = tag_name.lower()

        normalized_name = tag_name if case_sensitive else tag_name.lower()
        if normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)

        django_cache_key = f"tagpk:{model_label}:{'cs' if case_sensitive else 'ci'}:{normalized_name}"
        tag_pk = cache.get(django_cache_key)

        if tag_pk is not None:
            tag = tag_model.objects.filter(pk=tag_pk).first()
            if tag is None:
                cache.delete(django_cache_key)

        if tag_pk is None or tag is None:
            field_lookup = {"name": tag_name} if case_sensitive else {"name__iexact": tag_name}
            tag, __ = tag_model.objects.get_or_create(
                defaults={"name": tag_name, "protected": False},
                **field_lookup,
            )
            cache.set(django_cache_key, tag.pk, _TAG_CACHE_TTL)

        resolved_tags.append(tag)

    return resolved_tags


def cvss3_validator(value: str | list[str], exception_class: Callable = ValidationError) -> None:
    logger.debug("cvss3_validator called with value: %s", value)
    cvss_vectors = cvss.parser.parse_cvss_from_text(value)
    if len(cvss_vectors) > 0:
        vector_obj = cvss_vectors[0]

        if isinstance(vector_obj, CVSS3):
            # all is good
            return

        if isinstance(vector_obj, CVSS4):
            msg = "CVSS4 vector cannot be stored in the cvssv3 field. Use the cvssv4 field."
            raise exception_class(msg)
        if isinstance(vector_obj, CVSS2):
            msg = "Unsupported CVSS2 version detected."
            raise exception_class(msg)

        msg = "Unsupported CVSS version detected."
        raise exception_class(msg)

    # Explicitly raise an error if no CVSS vectors are found,
    # to avoid 'NoneType' errors during severity processing later.
    msg = "No valid CVSS3 vectors found by cvss.parse_cvss_from_text()"
    raise exception_class(msg)


def cvss4_validator(value: str | list[str], exception_class: Callable = ValidationError) -> None:
    logger.debug("cvss4_validator called with value: %s", value)
    cvss_vectors = cvss.parser.parse_cvss_from_text(value)
    if len(cvss_vectors) > 0:
        vector_obj = cvss_vectors[0]

        if isinstance(vector_obj, CVSS4):
            # all is good
            return

        if isinstance(vector_obj, CVSS3):
            msg = "CVSS3 vector cannot be stored in the cvssv4 field. Use the cvssv3 field."
            raise exception_class(msg)
        if isinstance(vector_obj, CVSS2):
            msg = "Unsupported CVSS2 version detected."
            raise exception_class(msg)

        msg = "Unsupported CVSS version detected."
        raise exception_class(msg)

    # Explicitly raise an error if no CVSS vectors are found,
    # to avoid 'NoneType' errors during severity processing later.
    msg = "No valid CVSS4 vectors found by cvss.parse_cvss_from_text()"
    raise exception_class(msg)


class ImporterFileExtensionValidator(FileExtensionValidator):
    default_allowed_extensions = [ext[1:] for ext in settings.FILE_IMPORT_TYPES]

    def __init__(self, *args: list, **kwargs: dict):
        if "allowed_extensions" not in kwargs:
            kwargs["allowed_extensions"] = self.default_allowed_extensions
        super().__init__(*args, **kwargs)

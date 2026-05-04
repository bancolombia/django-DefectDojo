import logging
from crum import get_current_user
from django.db.models import Exists, OuterRef, Q 

from dojo.authorization.authorization import get_roles_for_permission, user_has_global_permission
from dojo.models import (
    IMPORT_UNTOUCHED_FINDING,
    Product_Member,
    Product_Type_Member,
    TransferFinding,
)
from dojo.query_utils import build_count_subquery

logger = logging.getLogger(__name__)


def get_authorized_groups(permission, user=None):
    roles = get_roles_for_permission(permission)
    authorized_origin_product_type_roles = Product_Type_Member.objects.filter(
        product_type=OuterRef("origin_product_type"),
        user=user,
        role__in=roles)
    authorized_destination_product_type_roles = Product_Type_Member.objects.filter(
        product_type=OuterRef("destination_product_type"),
        user=user,
        role__in=roles)
    authorized_origin_product_roles = Product_Member.objects.filter(
        product=OuterRef("origin_product"),
        user=user,
        role__in=roles)
    authorized_destination_product_roles = Product_Member.objects.filter(
        product=OuterRef("destination_product"),
        user=user,
        role__in=roles)

    return (
        authorized_origin_product_type_roles,
        authorized_origin_product_roles,
        authorized_destination_product_type_roles,
        authorized_destination_product_roles,
    )


def get_authorized_transfer_finding(permission, queryset=None, user=None):
    if user is None:
        user = get_current_user()
    if user is None:
        return TransferFinding.objects.none()
    transfer_findings = TransferFinding.objects.all().order_by("id") if queryset is None else queryset

    if user.is_superuser:
        return transfer_findings

    if user_has_global_permission(user, permission):
        return transfer_findings

    (
        authorized_origin_product_type_roles,
        authorized_origin_product_roles,
        authorized_destination_product_type_roles,
        authorized_destination_product_roles,
    ) = get_authorized_groups(permission, user=user)

    transfer_findings = transfer_findings.annotate(
        origin_product_type_member=Exists(authorized_origin_product_type_roles),
        origin_product_member=Exists(authorized_origin_product_roles),
        destination_product_type_authorized=Exists(authorized_destination_product_type_roles),
        destination_product_authorized_group=Exists(authorized_destination_product_roles))
    return transfer_findings.filter(
        Q(origin_product_type_member=True)
        | Q(origin_product_member=True)
        | Q(destination_product_type_authorized=True)
        | Q(destination_product_authorized_group=True))
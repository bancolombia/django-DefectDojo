
from crum import get_current_user
from dojo.api_v2.scope.models import Input, InputEngagement
from dojo.models import Product_Member, Product_Type_Member
from django.db.models import OuterRef, Exists, Q
from dojo.authorization.authorization import get_roles_for_permission, user_has_global_permission


def get_authorized_scope(permission):
    user = get_current_user()

    if user is None:
        return Input.objects.none()

    if user.is_superuser:
        return Input.objects.all().order_by("id")

    if user_has_global_permission(user, permission):
        return Input.objects.all().order_by("id")


    roles = get_roles_for_permission(permission)
    authorized_product_type_roles = Product_Type_Member.objects.filter(
        product_type=OuterRef("product__prod_type_id"),
        user=user,
        role__in=roles)
    authorized_input_roles = Product_Member.objects.filter(
        product=OuterRef("product_id"),
        user=user,
        role__in=roles)
    
    input_engagement = InputEngagement.objects.annotate(
        product__prod_type__member=Exists(authorized_product_type_roles),
        product__member=Exists(authorized_input_roles)
        )
    input_engagement_ids = input_engagement.filter(
        Q(product__member=True) | Q(product__prod_type__member=True)).values_list("id", flat=True)
    input = Input.objects.filter(inputengagement__id__in=input_engagement_ids)
    return input

    
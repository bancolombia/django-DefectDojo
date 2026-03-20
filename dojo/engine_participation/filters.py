import django_filters
from dojo.engine_participation.models import HCParticipation


class HCParticipationFilter(django_filters.FilterSet):
    """Filter for HC Participation requests"""
    
    product_name = django_filters.CharFilter(
        field_name="product__name",
        lookup_expr="icontains",
        label="Product Name"
    )
    
    product_type = django_filters.NumberFilter(
        field_name="product__prod_type__id",
        label="Product Type"
    )
    
    status = django_filters.ChoiceFilter(
        choices=HCParticipation.STATUS_CHOICES,
        label="Status"
    )
    
    recommendation = django_filters.ChoiceFilter(
        choices=HCParticipation.RECOMMENDATION_CHOICES,
        label="Recommendation"
    )
    
    business_criticality = django_filters.CharFilter(
        lookup_expr="iexact",
        label="Business Criticality"
    )
    
    batch_id = django_filters.UUIDFilter(
        label="Batch ID"
    )
    
    create_date = django_filters.DateFromToRangeFilter(
        label="Creation Date"
    )
    
    class Meta:
        model = HCParticipation
        fields = [
            "product_name",
            "product_type",
            "status",
            "recommendation",
            "business_criticality",
            "batch_id",
            "create_date",
        ]

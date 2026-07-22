import django_filters
from dojo.engine_participation.models import HCParticipation


class HCParticipationFilter(django_filters.FilterSet):
    """Filter for HC Participation requests"""

    STATUS_FILTER_CHOICES = [
        ("Pending", "Pending"),
        ("Reviewed", "Reviewed"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
        ("Removal Approved", "Removal Approved"),
        ("Continues in HC", "Continues in HC"),
    ]
    
    product_name = django_filters.CharFilter(
        field_name="product__name",
        lookup_expr="icontains",
        label="Product Name"
    )
    
    product_type = django_filters.CharFilter(
        field_name="product__prod_type__name",
        lookup_expr="icontains",
        label="Product Type"
    )
    
    status = django_filters.ChoiceFilter(
        choices=STATUS_FILTER_CHOICES,
        method="filter_status",
        label="Status"
    )
    
    business_criticality = django_filters.ChoiceFilter(
        choices=HCParticipation.BUSSINESS_CRITICALITY_CHOICES,
        label="Business Criticality"
    )
    
    class Meta:
        model = HCParticipation
        fields = [
            "product_name",
            "product_type",
            "status",
            "business_criticality",
        ]

    def filter_status(self, queryset, _name, value):
        if not value:
            return queryset

        if value == "Removal Approved":
            return queryset.filter(status="Approved", recommendation="already_in_hc")

        if value == "Continues in HC":
            return queryset.filter(status="Rejected", recommendation="already_in_hc")

        if value == "Approved":
            return queryset.filter(status="Approved").exclude(recommendation="already_in_hc")

        if value == "Rejected":
            return queryset.filter(status="Rejected").exclude(recommendation="already_in_hc")

        return queryset.filter(status=value)

import django_filters as filter 
from dojo.engine_tools.models import FindingExclusion


class FindingExclusionFilter(filter.FilterSet):
    unique_id_from_tool = filter.CharFilter(method="filter_unique_id_from_tool")

    def filter_unique_id_from_tool(self, queryset, name, value):
        matching_ids = [
            exclusion.pk
            for exclusion in queryset
            if exclusion.has_unique_id(value.strip())
        ]
        return queryset.filter(pk__in=matching_ids)

    class Meta:
        model = FindingExclusion
        fields = ["uuid", "unique_id_from_tool", "type", "status"]

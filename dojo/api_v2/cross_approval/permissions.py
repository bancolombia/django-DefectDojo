from rest_framework import permissions

from dojo.engine_tools.helpers import Constants
from dojo.templatetags.authorization_tags import is_in_group


class IsCrossApprovalMaintainer(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        return is_in_group(request.user, Constants.REVIEWERS_MAINTAINER_GROUP.value)
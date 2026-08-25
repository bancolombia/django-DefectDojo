from rest_framework import permissions

from dojo.templatetags.authorization_tags import has_permission_to_cross_approval


class IsCrossApprovalMaintainer(permissions.BasePermission):
    def has_permission(self, request, view):
        return has_permission_to_cross_approval(request.user)
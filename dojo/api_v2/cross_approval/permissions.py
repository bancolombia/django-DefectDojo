from django.conf import settings
from rest_framework import permissions

from dojo.models import GeneralSettings


def _configured_groups(setting_name):
    if setting_name == "GROUPS_TO_CROSS_SUBMITER":
        groups = GeneralSettings.get_value(setting_name, settings.REVIEWER_GROUP_NAME)
    else:
        groups = getattr(settings, setting_name)
    if isinstance(groups, str):
        return [group.strip() for group in groups.split(",") if group.strip()]
    return [group.strip() for group in groups if isinstance(group, str) and group.strip()]


def _is_in_group(user, group_name):
    return user.is_superuser or user.groups.filter(dojo_group__name=group_name).exists()


def is_cross_approval_submitter(user):
    if user.is_superuser:
        return True
    return any(
        _is_in_group(user, group_name)
        for group_name in _configured_groups("GROUPS_TO_CROSS_SUBMITER")
    )


def is_cross_approval_reviewer(user):
    if user.is_superuser:
        return True
    reviewer_groups = _configured_groups("REVIEWER_GROUP_NAME")
    approver_groups = _configured_groups("APPROVER_GROUP_NAME")
    return any(
        _is_in_group(user, group_name)
        for group_name in reviewer_groups + approver_groups
    )


class IsCrossApprovalSubmitter(permissions.BasePermission):
    def has_permission(self, request, view):
        return is_cross_approval_submitter(request.user) or is_cross_approval_reviewer(request.user)


class IsCrossApprovalReviewer(permissions.BasePermission):
    def has_permission(self, request, view):
        return is_cross_approval_reviewer(request.user)
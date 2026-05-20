from dojo.authorization.roles_permissions import Roles, get_roles_with_permissions
from dojo.authorization.roles_permissions import Permissions
from dojo.authorization.exclusive_permissions import get_members
import dojo.risk_acceptance.helper as helper_ra
import dojo.transfer_findings.helper as helper_tf
from dojo.api_v2.scope.models import Input
from dojo.models import Finding


def validation_status_permission(finding, permissions):
    button_dict = {
        "Risk_Acceptance": helper_ra.enable_flow_accept_risk,
        "Transfer_Finding_Add": helper_tf.enable_flow_transfer_finding,
        "Transfer_Finding_Finding_Add": helper_tf.enable_flow_transfer_finding,
    }

    for perm in list(permissions):
        if perm.name in button_dict:
            function_action = button_dict[perm.name]
            if not function_action(finding=finding):
                permissions.remove(perm)

    return permissions

def get_global_role(user):
    if hasattr(user, "global_role"):
        if user.global_role:
            if user.global_role.role:
                if user.global_role.role.name in Roles.get_roles():
                    return user.global_role.role.name

def user_has_permission(user, obj):
    if user.is_anonymous:
        return []

    if user.is_superuser:
        return ["all"]
    role = get_global_role(user)

    if role is None:

        if isinstance(obj, Input):
            if user == obj.owner:
                return Permissions.get_input_permissions()
        elif isinstance(obj, Finding):
            members = get_members(user, obj)
            if members:
                role = members.role.name
                roles = get_roles_with_permissions()
                permissions = roles.get(Roles[role])
                return validation_status_permission(obj, permissions)
    else:
        roles = get_roles_with_permissions()
        permissions = roles.get(Roles[role])
        if isinstance(obj, Input):
            if user == obj.owner:
                return Permissions.get_input_permissions()
        else:
            return validation_status_permission(obj, permissions)
    return []



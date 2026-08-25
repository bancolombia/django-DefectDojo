from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.middleware.csrf import get_token
from django.shortcuts import render

from dojo.templatetags.authorization_tags import has_permission_to_cross_approval
from dojo.utils import add_breadcrumb


def crossapproval_list(request):
    if not has_permission_to_cross_approval(request.user):
        raise PermissionDenied

    token = get_token(request)
    session_id = request.COOKIES.get("sessionid", "")
    params = f"?csrftoken={token}&sessionid={session_id}"
    add_breadcrumb(title="Cross-approval of suppliers", top_level=True, request=request)
    return render(request, "dojo/crossapproval.html", {
        "url": f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/cross-approval/list{params}",
        "name": "Cross-approval of suppliers",
    })
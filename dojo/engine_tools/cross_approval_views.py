from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.middleware.csrf import get_token
from django.shortcuts import render

from dojo.api_v2.cross_approval.permissions import is_cross_approval_reviewer, is_cross_approval_submitter
from dojo.utils import add_breadcrumb


def crossapproval_list(request):
    if not request.user.is_authenticated:
        raise PermissionDenied

    token = get_token(request)
    session_id = request.COOKIES.get("sessionid", "")
    params = (
        f"?csrftoken={token}&sessionid={session_id}"
        f"&cross_approval_can_submit={'true' if is_cross_approval_submitter(request.user) else 'false'}"
        f"&cross_approval_can_review={'true' if is_cross_approval_reviewer(request.user) else 'false'}"
    )
    add_breadcrumb(title="Cross-approval of suppliers", top_level=True, request=request)
    return render(request, "dojo/crossapproval.html", {
        "url": f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/cross-approval/list{params}",
        "name": "Cross-approval of suppliers",
    })
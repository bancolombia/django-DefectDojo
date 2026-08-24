from django.conf import settings
from django.middleware.csrf import get_token
from django.shortcuts import render

from dojo.utils import add_breadcrumb


def crossapproval_list(request):
    token = get_token(request)
    session_id = request.COOKIES.get("sessionid", "")
    params = f"?csrftoken={token}&sessionid={session_id}"
    add_breadcrumb(title="Cross-approval of suppliers", top_level=True, request=request)
    return render(request, "dojo/crossapproval.html", {
        "url": f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/cross-approval/list{params}",
        "name": "Cross-approval of suppliers",
    })
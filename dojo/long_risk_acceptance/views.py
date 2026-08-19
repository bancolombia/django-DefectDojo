from django.conf import settings
from django.db.models.base import Model as Model
from dojo.decorators import dojo_ratelimit_view
from django.middleware.csrf import get_token
from dojo.utils import add_breadcrumb
from django.http import HttpResponse, HttpRequest
from django.shortcuts import get_object_or_404, render

@dojo_ratelimit_view()
def view_long_risk_acceptance_details(request: HttpRequest, pk: int) -> HttpResponse:
    page_name = ('view_long_risk_acceptance_details')
    user = request.user.id
    cookie_csrftoken = get_token(request)
    cookie_sessionid = request.COOKIES.get('sessionid', '')
    base_params = f"?csrftoken={cookie_csrftoken}&sessionid={cookie_sessionid}"
    base_params += f"&longid={pk}"
    add_breadcrumb(title=page_name, request=request, top_level=False)
    return render(request, 'dojo/generic_view.html', {
        'actions': page_name,
        'url': f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/long-term-acceptance/detail{base_params}",
        'user': user})

@dojo_ratelimit_view()
def view_long_risk_acceptance_list(request: HttpRequest) -> HttpResponse:
    page_name = ('view_long_risk_acceptance_list')
    user = request.user.id
    cookie_csrftoken = get_token(request)
    cookie_sessionid = request.COOKIES.get('sessionid', '')
    base_params = f"?csrftoken={cookie_csrftoken}&sessionid={cookie_sessionid}"
    add_breadcrumb(title=page_name, request=request, top_level=False)
    return render(request, 'dojo/generic_view.html', {
        'actions': page_name,
        'url': f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/long-term-acceptance/list{base_params}",
        'user': user})

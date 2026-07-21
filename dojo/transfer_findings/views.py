from django.conf import settings
from django.db.models.base import Model as Model
from django.db.models.query import QuerySet
from django.views import View
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from dojo.decorators import dojo_ratelimit_view
from django.middleware.csrf import get_token
from dojo.utils import add_breadcrumb
from django.views.generic.edit import UpdateView
from django.http import HttpResponse, HttpRequest
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, render
from dojo.authorization.roles_permissions import Permissions
from dojo.utils import redirect_to_return_url_or_else
from dojo.authorization.authorization import user_has_permission_or_403
from dojo.transfer_findings.forms import DeleteTransferFindingForm, UpdateTransferFindingForm
from dojo.models import TransferFinding
from dojo.forms import TransferFindingForm
from dojo.transfer_findings import helper as helper_tf


class TransferFindingDeleteView(View):
    def get_transfer_finding(self, transfer_finding_id: int):
        return get_object_or_404(TransferFinding, id=transfer_finding_id)

    def process_form(self, request: HttpRequest, transfer_finding: TransferFinding, context: dict):
        if context["form"].is_valid():
            transfer_finding.delete()
            messages.add_message(
                request,
                messages.SUCCESS,
                "Transfer-Findig deleted successfully.",
                extra_tags="alert-success",
            )
            return request, True

        messages.add_message(
            request,
            messages.ERROR,
            "Unable to delete Transfer-Finding, please try again.",
            extra_tags="alert-danger",
        )
        return request, False
    
    def post(self, request: HttpRequest):
        transfer_finding_id = request.POST["id"]
        transfer_finding = get_object_or_404(TransferFinding, id=transfer_finding_id)
        user_has_permission_or_403(request.user, transfer_finding, Permissions.Transfer_Finding_Delete)
        context = {
            "form": DeleteTransferFindingForm(request.POST, instance=transfer_finding),
        }
        if helper_tf.delete_transfer_finding_finding(transfer_finding):
            request, success = self.process_form(request, transfer_finding, context)
            if success:
                return redirect_to_return_url_or_else(request, reverse("product", args=(transfer_finding.destination_product.id,)))
            raise PermissionDenied
        else:
            raise InterruptedError


class TransferFindingUpdateView(View):
    def get_template(self):
        return 'dojo/transferfinding_update_form.html'

    def get(self, request, pk):
        transfer_finding = get_object_or_404(TransferFinding, pk=pk)
        form = UpdateTransferFindingForm(instance=transfer_finding)
        return render(request, self.get_template(), {'form': form})

    def post(self, request, pk):
        transfer_finding = get_object_or_404(TransferFinding, pk=pk)
        form = UpdateTransferFindingForm(request.POST, instance=transfer_finding)

        if form.is_valid():
            form.save()
            return redirect_to_return_url_or_else(request, reverse("product", args=(transfer_finding.destination_product.id,)))

        return render(request, self.get_template(), {'form': form})


@dojo_ratelimit_view()
def view_transfer_finding_v2(request: HttpRequest, pk: int) -> HttpResponse:
    page_name = ('view_details_transfer_finding')
    user = request.user.id
    cookie_csrftoken = get_token(request)
    cookie_sessionid = request.COOKIES.get('sessionid', '')
    base_params = f"?csrftoken={cookie_csrftoken}&sessionid={cookie_sessionid}"
    base_params += f"&transfer={pk}"
    add_breadcrumb(title=page_name, request=request)
    return render(request, 'dojo/generic_view.html', {
        'actions': page_name,
        'url': f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/findings/detail-transfer{base_params}",
        'user': user})

@dojo_ratelimit_view()
def view_sent_transfer(request: HttpRequest, pk: int) -> HttpResponse:
    page_name = ('view_sent_transfer')
    user = request.user.id
    cookie_csrftoken = get_token(request)
    cookie_sessionid = request.COOKIES.get('sessionid', '')
    base_params = f"?csrftoken={cookie_csrftoken}&sessionid={cookie_sessionid}"
    base_params += f"&product={pk}"
    add_breadcrumb(title=page_name, request=request, top_level=False)
    return render(request, 'dojo/generic_view.html', {
        'actions': page_name,
        'url': f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/findings/list-transfer{base_params}",
        'user': user})

@dojo_ratelimit_view()
def view_received_transfer(request: HttpRequest, pk: int) -> HttpResponse:
    page_name = ('view_received_transfer')
    user = request.user.id
    cookie_csrftoken = get_token(request)
    cookie_sessionid = request.COOKIES.get('sessionid', '')
    base_params = f"?csrftoken={cookie_csrftoken}&sessionid={cookie_sessionid}"
    base_params += f"&destination={pk}"
    add_breadcrumb(title=page_name, request=request, top_level=False)
    return render(request, 'dojo/generic_view.html', {
        'actions': page_name,
        'url': f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/findings/list-transfer{base_params}",
        'user': user})

@dojo_ratelimit_view()
def view_all_transfer(request: HttpRequest) -> HttpResponse:
    page_name = ('view_all_transfer')
    user = request.user.id
    cookie_csrftoken = get_token(request)
    cookie_sessionid = request.COOKIES.get('sessionid', '')
    base_params = f"?csrftoken={cookie_csrftoken}&sessionid={cookie_sessionid}"
    add_breadcrumb(title=page_name, request=request, top_level=True)
    return render(request, 'dojo/generic_view.html', {
        'actions': page_name,
        'url': f"{settings.MF_FRONTEND_DEFECT_DOJO_URL}/findings/list-transfer{base_params}",
        'user': user})
from django.db import models
from django.utils.translation import gettext_lazy as _

class RiskAcceptanceEngagement(models.Model):
    product = models.ForeignKey(
        "Product", null=True, blank=True, on_delete=models.CASCADE
    )
    description = models.TextField(blank=True, null=True)
    accepted_by = models.CharField(max_length=200, default=None, null=True, blank=True, verbose_name=_("Accepted By"), help_text=_("The person that accepts the risk, can be outside of DefectDojo."))
    reviewed_by = models.CharField(max_length=200, default=None, null=True, blank=True, verbose_name=_("Reviewed By"), help_text=_("The person that reviews the risk acceptance for acceptance long term"))
    reviewed_date = models.DateTimeField(default=None, null=True, blank=True, help_text=_("When the risk acceptance is reviewed"))
    accepted_date = models.DateTimeField(default=None, null=True, blank=True, help_text=_("When the risk acceptance is accepted"))
    expiration_date = models.DateTimeField(default=None, null=True, blank=True, help_text=_("When the risk acceptance expires, the findings will be reactivated (unless disabled below)."))
    expiration_date_warned = models.DateTimeField(default=None, null=True, blank=True, help_text=_("(readonly) Date at which notice about the risk acceptance expiration was sent."))
    expiration_date_handled = models.DateTimeField(default=None, null=True, blank=True, help_text=_("(readonly) When the risk acceptance expiration was handled (manually or by the daily job)."))
    reactivate_expired = models.BooleanField(null=False, blank=False, default=True, verbose_name=_("Reactivate findings on expiration"), help_text=_("Reactivate findings when risk acceptance expires?"))
    owner = models.ForeignKey("Dojo_User", editable=True, null=True, on_delete=models.RESTRICT, help_text=_("User in DefectDojo owning this acceptance. Only the owner and staff users can edit the risk acceptance."))
    notes = models.ManyToManyField("Notes", editable=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)


class RiskAcceptanceExclusionRule(models.Model):
    ra_engagement = models.ForeignKey(RiskAcceptanceEngagement, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    filters = models.JSONField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
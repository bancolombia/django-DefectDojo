import uuid
from django.db import models
from django.contrib import admin
from django.utils.translation import gettext as _


class HCParticipation(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Reviewed", "Reviewed"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
        ("Cancelled", "Cancelled"),
    ]
    
    RECOMMENDATION_CHOICES = [
        ("postulated", "Postulated to Continuous Pentesting"),
        ("manual_postulated", "Manually Postulated to Continuous Pentesting"),
        ("already_in_hc", "Already in Continuous Pentesting"),
        ("not_eligible", "Not eligible"),
    ]
    
    BUSSINESS_CRITICALITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("very high", "Very High"),
    ]
    
    uuid = models.UUIDField(default=uuid.uuid4, primary_key=True)
    
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="hc_participations",
        help_text=_("Product being evaluated for HC participation")
    )
    
    recommendation = models.CharField(
        max_length=20,
        choices=RECOMMENDATION_CHOICES,
        help_text=_("System recommendation based on business rules")
    )
    
    business_criticality = models.CharField(
        max_length=20,
        choices=BUSSINESS_CRITICALITY_CHOICES,
        null=True,
        blank=True,
        help_text=_("Business criticality at evaluation time")
    )
    
    was_in_hacking_continuous = models.BooleanField(
        default=False,
        help_text=_("Whether product was already in HC at evaluation time")
    )
    
    security_posture_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Security posture snapshot at evaluation time")
    )
    
    reason = models.TextField(
        blank=True,
        help_text=_("System-generated reason for the recommendation")
    )
    
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default="Pending",
        help_text=_("Current status in approval workflow")
    )
    
    final_status = models.CharField(
        max_length=12,
        choices=[("Approved", "Approved"), ("Rejected", "Rejected")],
        blank=True,
        null=True,
        help_text=_("Final decision after review")
    )
    
    create_date = models.DateTimeField(auto_now_add=True)
    last_status_update = models.DateTimeField(auto_now=True)
    
    status_updated_at = models.DateTimeField(null=True, blank=True)
    status_updated_by = models.ForeignKey(
        "Dojo_User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hc_status_updates"
    )
    
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "Dojo_User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hc_reviews"
    )
    
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "Dojo_User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hc_approvals"
    )
    
    rejected_by = models.ForeignKey(
        "Dojo_User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hc_rejections"
    )
    
    created_by = models.ForeignKey(
        "Dojo_User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hc_created"
    )
    
    batch_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Groups evaluations from same batch execution")
    )
    
    notification_sent = models.BooleanField(default=False)
    
    class Meta:
        app_label = "dojo"
        db_table = "dojo_hc_participation"
        ordering = ["-create_date"]
        verbose_name = "HC Participation Request"
        verbose_name_plural = "HC Participation Requests"
        indexes = [
            models.Index(fields=["product", "-create_date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["recommendation"]),
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.recommendation} ({self.status})"


class HCParticipationDiscussion(models.Model):
    hc_participation = models.ForeignKey(
        HCParticipation,
        on_delete=models.CASCADE,
        related_name="discussions"
    )
    author = models.ForeignKey("Dojo_User", on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = "dojo"
        db_table = "dojo_hc_participation_discussion"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"Discussion by {self.author.username} on {self.created_at}"


class HCParticipationLog(models.Model):
    hc_participation = models.ForeignKey(
        HCParticipation,
        on_delete=models.CASCADE,
        related_name="logs"
    )
    changed_by = models.ForeignKey("Dojo_User", on_delete=models.CASCADE)
    previous_status = models.CharField(
        max_length=12,
        choices=HCParticipation.STATUS_CHOICES,
        blank=True
    )
    current_status = models.CharField(
        max_length=12,
        choices=HCParticipation.STATUS_CHOICES
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        app_label = "dojo"
        db_table = "dojo_hc_participation_log"
        ordering = ["-changed_at"]
    
    def __str__(self):
        return f"Log for {self.hc_participation.uuid} - {self.current_status}"


admin.site.register(HCParticipation)
admin.site.register(HCParticipationDiscussion)
admin.site.register(HCParticipationLog)

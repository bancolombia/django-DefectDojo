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
        ("postulated", "Postulated to HC"),
        ("already_in_hc", "Already in Hacking Continuous"),
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
            models.Index(
                fields=["recommendation", "-create_date"],
                name="dojo_hc_par_recomm_eefdf6_idx",
            ),
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


class HCEvaluationRun(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Celery task ID for tracking async execution"),
    )
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    triggered_by = models.ForeignKey(
        "Dojo_User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hc_evaluation_runs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    total_candidates = models.IntegerField(
        default=0,
        help_text=_("Number of products that passed the CLASSID filter"),
    )
    processed_count = models.IntegerField(
        default=0,
        help_text=_("Products processed so far (updated periodically)"),
    )
    result_summary = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Final counts per recommendation type"),
    )
    log_entries = models.JSONField(
        default=list,
        help_text=_("Execution log entries [{timestamp, level, message}]"),
    )
    error_message = models.TextField(blank=True, null=True)
    create_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "dojo"
        db_table = "dojo_hc_evaluation_run"
        ordering = ["-create_date"]
        verbose_name = "HC Evaluation Run"
        verbose_name_plural = "HC Evaluation Runs"

    def __str__(self):
        return f"HCEvaluationRun {self.id} [{self.status}] - {self.create_date}"

    @property
    def progress_pct(self):
        if self.total_candidates == 0:
            return 100 if self.status == self.STATUS_COMPLETED else 0
        return min(100, round(self.processed_count * 100 / self.total_candidates))

    @property
    def duration_seconds(self):
        if not self.started_at:
            return None
        end = self.finished_at or __import__("django.utils.timezone", fromlist=["timezone"]).timezone.now()
        return round((end - self.started_at).total_seconds())


admin.site.register(HCParticipation)
admin.site.register(HCParticipationDiscussion)
admin.site.register(HCParticipationLog)

from django.db import models
from django.contrib import admin
from django.utils.translation import gettext as _
from django.utils.safestring import mark_safe

import uuid


class FindingExclusion(models.Model):
    TYPE_CHOICES = [("white_list", "white_list"),
                    ("black_list", "black_list")]
    STATUS_CHOICES = [("Accepted", "Accepted"),
                      ("Pending", "Pending"),
                      ("Reviewed", "Reviewed"),
                      ("Rejected", "Rejected"),
                      ("Expired", "Expired")]
    uuid = models.UUIDField(default=uuid.uuid4, primary_key=True)
    type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    unique_id_from_tool = models.CharField(
        blank=True,
        max_length=500,
        verbose_name=_("Vulnerability Id"),
        help_text=_("Vulnerability technical id from the source tool. Allows to track unique vulnerabilities."))

    create_date = models.DateTimeField(auto_now_add=True)
    notification_sent = models.BooleanField(default=False)
    expiration_date = models.DateTimeField(null=True)
    last_status_update = models.DateTimeField(auto_now=True)
    status_updated_at = models.DateTimeField(null=True)
    status_updated_by = models.ForeignKey("Dojo_User",
                                          null=True,
                                          related_name="dojo_user_status_updated",
                                          on_delete=models.CASCADE)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=8, choices=STATUS_CHOICES, blank=True, default="Pending")
    final_status = models.CharField(
        choices=[("Accepted", "Accepted"), ("Rejected", "Rejected")], blank=True, null=True)
    created_by = models.ForeignKey("Dojo_User",
                                   null=True,
                                   blank=True,
                                   on_delete=models.CASCADE,
                                   related_name="dojo_user_created")
    reviewed_by = models.ForeignKey("Dojo_User",
                                    null=True,
                                    blank=True,
                                    on_delete=models.CASCADE,
                                    related_name="dojo_user_reviewed")
    accepted_by = models.ForeignKey("Dojo_User",
                                    null=True,
                                    blank=True,
                                    on_delete=models.CASCADE,
                                    related_name="dojo_user_accepted")
    rejected_by = models.ForeignKey("Dojo_User",
                                    null=True,
                                    blank=True,
                                    on_delete=models.CASCADE,
                                    related_name="dojo_user_rejected")
    practice = models.CharField(max_length=50, null=True, blank=True)
    
    product_type = models.ForeignKey("Product_Type",
                                     null=True,
                                     blank=True,
                                     on_delete=models.DO_NOTHING,
                                     related_name="product_type")
    
    product = models.ForeignKey("Product",
                                     null=True,
                                     blank=True,
                                     on_delete=models.DO_NOTHING,
                                     related_name="product")
    
    engagement = models.ForeignKey("Engagement",
                                     null=True,
                                     blank=True,
                                     on_delete=models.DO_NOTHING,
                                     related_name="engagement")

    def save(self, *args, **kwargs):
        is_update = self.pk is not None

        if is_update:
            try:
                original = FindingExclusion.objects.get(pk=self.pk)
            except FindingExclusion.DoesNotExist:
                original = None
        else:
            original = None

        super().save(*args, **kwargs)

        if original and original.status != self.status:
            FindingExclusionStatusHistorical.objects.create(
                finding_exclusion=self,
                last_status=original.status,
                new_status=self.status,
                user=self.status_updated_by
            )

    class Meta:
        db_table = "dojo_finding_exlusion"


class FindingExclusionDiscussion(models.Model):
    finding_exclusion = models.ForeignKey(
        "FindingExclusion",
        on_delete=models.CASCADE,
        related_name='discussions'
    )
    author = models.ForeignKey("Dojo_User", on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Discussion by {self.author.username} on {self.created_at}"

    class Meta:
        db_table = "dojo_finding_exclusion_discussion"


class FindingExclusionStatusHistorical(models.Model):
    finding_exclusion = models.ForeignKey(
        'FindingExclusion', on_delete=models.CASCADE, related_name='historical'
    )
    last_status = models.CharField(
        max_length=8,
        choices=FindingExclusion.STATUS_CHOICES,
        default="Pending"
    )
    new_status = models.CharField(
        max_length=8,
        choices=FindingExclusion.STATUS_CHOICES,
        default="Pending"
    )
    change_date = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        "Dojo_User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-change_date"]

    def to_html_log(self) -> str:
        icon = "🔁"
        STATUS_COLOR = {
            "Pending": "#1B30DE",
            "Accepted": "#096C11",
            "Rejected": "#d11d38",
            "Expired": "#d11d38"
        }
        DEFAULT_COLOR = "#b97a0c"

        return mark_safe(f'''
        <div class = "d-flex align-items-start p-2 text-light rounded"
             style = "margin-bottom: 10px" >
            <code style="color: black">
                <span class="me-2">{icon}</span>
                <strong>{self.change_date.strftime('%Y-%m-%d %H:%M')}</strong>
                Status changed from
                <span class="pass_fail Pass"
                      style="background-color: {STATUS_COLOR.get(self.last_status, DEFAULT_COLOR)}">
                    {self.last_status}
                </span>
                to
                <span class="pass_fail Pass"
                      style="background-color: {STATUS_COLOR.get(self.new_status, DEFAULT_COLOR)}">
                    {self.new_status}
                </span>
                by 👤<strong>{self.user}</strong>
            </code>
        </div>
        ''')


admin.site.register(FindingExclusion)
admin.site.register(FindingExclusionDiscussion)

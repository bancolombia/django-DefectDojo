from django import forms
from django.conf import settings

from dojo.engine_participation.models import HCParticipationDiscussion


class HCParticipationDiscussionForm(forms.ModelForm):
    class Meta:
        model = HCParticipationDiscussion
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Add a comment..."
            })
        }
        labels = {
            "content": "Comment"
        }


class HCManualPostulationForm(forms.Form):
    """Form used to collect the criteria met by a product before creating
    a manual Hacking Continuous postulation request."""

    criteria = forms.MultipleChoiceField(
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="Criteria met by the product",
        error_messages={
            "required": "You must select at least one criterion to submit the manual postulation."
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        criteria_choices = list(getattr(settings, "HC_MANUAL_POSTULATION_CRITERIA", []))
        self.fields["criteria"].choices = [(criterion, criterion) for criterion in criteria_choices]


class HCConfirmIngressPostulationForm(forms.Form):
    """Checklist required for reviewers before moving a postulated
    request to Reviewed."""

    criteria = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Checklist to confirm ingress postulation",
        error_messages={
            "required": "You must confirm at least one ingress checklist criterion to mark as reviewed."
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        criteria_choices = list(getattr(settings, "HC_CONFIRM_INGRESS_POSTULATION_CRITERIA", []))
        self.fields["criteria"].choices = [(criterion, criterion) for criterion in criteria_choices]
        self.requires_selection = bool(criteria_choices)
        self.fields["criteria"].required = self.requires_selection

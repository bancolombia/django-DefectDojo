from django import forms

from dojo.engine_participation.models import HCParticipationDiscussion
from dojo.engine_participation.helpers import (
    get_hc_confirm_ingress_postulation_criteria,
    get_hc_manual_postulation_criteria,
)


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
        criteria_choices = get_hc_manual_postulation_criteria()
        self.fields["criteria"].choices = [(criterion, criterion) for criterion in criteria_choices]


class HCConfirmIngressPostulationForm(forms.Form):
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
        criteria_choices = get_hc_confirm_ingress_postulation_criteria()
        self.fields["criteria"].choices = [(criterion, criterion) for criterion in criteria_choices]
        self.requires_selection = bool(criteria_choices)
        self.fields["criteria"].required = self.requires_selection

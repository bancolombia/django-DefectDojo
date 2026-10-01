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


class HCPreselectionForm(forms.Form):
    criteria = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Checklist to confirm ingress postulation",
    )
    scope = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Indicate the scope the tests should have (what you consider should be tested)...."
        }),
        label="Scope of the test",
        error_messages={"required": "You must indicate the scope the tests should have."}
    )
    description = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Describe the product and the reason for its postulation..."
        }),
        label="Description of the product and reason for postulation",
        error_messages={"required": "You must describe the product and the reason for the postulation."}
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configured_criteria = get_hc_confirm_ingress_postulation_criteria()
        self.fields["criteria"].choices = [(criterion, criterion) for criterion in self.configured_criteria]

    def clean_criteria(self):
        selected = self.cleaned_data.get("criteria", [])
        if self.configured_criteria and set(selected) != set(self.configured_criteria):
            raise forms.ValidationError(
                "You must confirm all ingress checklist criteria to pre-select this request."
            )
        return selected

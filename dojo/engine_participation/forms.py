from django import forms
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

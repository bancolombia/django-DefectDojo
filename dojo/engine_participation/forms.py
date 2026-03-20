from django import forms
from dojo.engine_participation.models import HCParticipation, HCParticipationDiscussion
from dojo.models import Product, Product_Type


class RunHCEvaluationForm(forms.Form):
    """Form for running HC participation evaluation"""
    
    product_type = forms.ModelChoiceField(
        queryset=Product_Type.objects.all().order_by("name"),
        required=False,
        label="Product Type",
        help_text="Filter evaluation by product type (optional)"
    )
    
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.all(),
        required=False,
        label="Specific Products",
        help_text="Evaluate only specific products (optional)",
        widget=forms.SelectMultiple(attrs={"class": "form-control"})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if "product_type" in self.data:
            try:
                product_type_id = int(self.data.get("product_type"))
                self.fields["products"].queryset = Product.objects.filter(
                    prod_type_id=product_type_id
                ).order_by("name")
            except (ValueError, TypeError):
                pass


class HCParticipationDiscussionForm(forms.ModelForm):
    """Form for adding discussions/comments to HC participation requests"""
    
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


class EditHCParticipationForm(forms.ModelForm):
    """Form for editing HC participation requests (admin only)"""
    
    class Meta:
        model = HCParticipation
        fields = [
            "status",
            "reason",
        ]
        widgets = {
            "reason": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3
            }),
            "status": forms.Select(attrs={
                "class": "form-control"
            })
        }

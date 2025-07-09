from django import forms
from dojo.engine_tools.models import FindingExclusion, FindingExclusionDiscussion
from dojo.engine_tools.helpers import Constants
from dojo.models import Product_Type, Product, Engagement


class CreateFindingExclusionForm(forms.ModelForm):
    type = forms.ChoiceField(required=True,
                             choices=FindingExclusion.TYPE_CHOICES)
    unique_id_from_tool = forms.CharField(
        required=True,
        max_length=500,
        help_text=Constants.VULNERABILITY_ID_HELP_TEXT.value)
    reason = forms.CharField(max_length=200, required=True,
                             widget=forms.Textarea,
                             label="Reason",
                             help_text="Please provide a reason for excluding this vulnerability id.")
    
    practice = forms.CharField(required=False,
                                label="Practice Origin Exclusion",
                                help_text="practice where exclusion originates",)
    
    product_type = forms.ModelChoiceField(
        label="Product Type",
        queryset=Product_Type.objects.all(),
        required=True
    )

    product = forms.ModelChoiceField(
        label="Product",
        queryset=Product.objects.none(),
        required=True
    )

    engagement = forms.ModelChoiceField(
        label="Engagement",
        queryset=Engagement.objects.none(),
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dynamically update product queryset based on product_type
        if 'product_type' in self.initial:
            product_type = self.initial['product_type']
            self.fields['product'].queryset = Product.objects.filter(prod_type=product_type)

        # Dynamically update engagement queryset based on product
        if 'product' in self.initial:
            product = self.initial['product']
            self.fields['engagement'].queryset = Engagement.objects.filter(product=product)
        
        if self.initial.get("practice"):
            self.fields.pop("practice")


    def clean(self):
        cleaned_data = super().clean()
        product_type = cleaned_data.get('product_type')
        product = cleaned_data.get('product')

        # Update product queryset based on selected product_type
        if product_type:
            self.fields['product'].queryset = Product.objects.filter(prod_type=product_type)

        # Update engagement queryset based on selected product
        if product:
            self.fields['engagement'].queryset = Engagement.objects.filter(product=product)

        return cleaned_data
    
    class Meta:
        model = FindingExclusion
        fields = ["type", "unique_id_from_tool", "reason", "practice"]
        

class EditFindingExclusionForm(forms.ModelForm):

    class Meta:
        model = FindingExclusion
        fields = ["type", "unique_id_from_tool", "reason", "expiration_date", "status"]
        widgets = {
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expiration_date"].required = False
    
    
class FindingExclusionDiscussionForm(forms.ModelForm):
    class Meta:
        model = FindingExclusionDiscussion
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Add a comment...'})
        }

from django import forms
from dojo.api_v2.validators import valid_chars_validator
from dojo.templatetags.authorization_tags import is_in_reviewer_group
from dojo.engine_tools.models import FindingExclusion, FindingExclusionDiscussion
from dojo.models import Product, Product_Type, Engagement
from dojo.engine_tools.helpers import Constants


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
    
    scope = forms.ChoiceField(
        choices=[('all', 'All Engagements'), ('specific', 'Specific Engagements')],
        widget=forms.RadioSelect,
        initial='all',
        label="Scope"
    )
    
    product_type = forms.ModelChoiceField(
        queryset=Product_Type.objects.all().order_by('name'),
        required=False,
        label="Product Type"
    )
    
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        required=False,
        label="Product"
    )
    
    engagements = forms.ModelMultipleChoiceField(
        queryset=Engagement.objects.none(),
        required=False,
        label="Engagements"
    )
    
    class Meta:
        model = FindingExclusion
        fields = ["type", "unique_id_from_tool", "reason", "practice", "scope", "product_type", "product", "engagements"]

    def _split_unique_ids(self, value):
        return [unique_id.strip() for unique_id in value.splitlines() if unique_id.strip()]

    def _clean_unique_ids(self, value):
        unique_ids = self._split_unique_ids(value)

        if not unique_ids:
            raise forms.ValidationError("This field is required.")

        if not self.allow_multiple_unique_ids and len(unique_ids) > 1:
            raise forms.ValidationError(
                "This flow only accepts a single Vulnerability Id."
            )

        deduplicated_unique_ids = []
        seen_unique_ids = set()
        for unique_id in unique_ids:
            if "," in unique_id:
                raise forms.ValidationError(
                    "Commas are not allowed inside a Vulnerability Id."
                )

            valid_chars_validator(unique_id)
            if unique_id not in seen_unique_ids:
                deduplicated_unique_ids.append(unique_id)
                seen_unique_ids.add(unique_id)

        normalized_unique_ids = FindingExclusion.normalize_unique_ids(deduplicated_unique_ids)
        if len(normalized_unique_ids) > self.fields["unique_id_from_tool"].max_length:
            raise forms.ValidationError(
                "The combined Vulnerability Ids exceed the maximum allowed length."
            )

        self.cleaned_unique_ids = deduplicated_unique_ids
        return normalized_unique_ids
    
    
    def clean_unique_id_from_tool(self):
        value = (self.cleaned_data.get("unique_id_from_tool") or "").strip()
        return self._clean_unique_ids(value)

    def clean_reason(self):
        value = self.cleaned_data.get("reason")
        valid_chars_validator(value)
        return value

    def clean_practice(self):
        value = self.cleaned_data.get("practice")
        valid_chars_validator(value)
        return value

        
    def __init__(self, user, *args, **kwargs):
        self.allow_multiple_unique_ids = kwargs.pop("allow_multiple_unique_ids", False)
        self.user = user
        super().__init__(*args, **kwargs)

        if self.allow_multiple_unique_ids:
            self.fields["unique_id_from_tool"].widget = forms.Textarea(attrs={"rows": 6})
            self.fields["unique_id_from_tool"].help_text = (
                "Enter one Vulnerability Id per line. All values will be stored in the same exclusion."
            )
        
        if not is_in_reviewer_group(self.user):
            self.fields.pop("scope")

        if self.initial.get("practice"):
            self.fields.pop("practice")

        if 'product_type' in self.data:
            try:
                product_type_id = int(self.data.get('product_type'))
                self.fields['product'].queryset = Product.objects.filter(prod_type_id=product_type_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.product_type:
             self.fields['product'].queryset = self.instance.product_type.product_set.order_by('name')

        if 'product' in self.data:
            try:
                product_id = int(self.data.get('product'))
                self.fields['engagements'].queryset = Engagement.objects.filter(product_id=product_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.product:
            self.fields['engagements'].queryset = self.instance.product.engagement_set.order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        scope = cleaned_data.get("scope")
        
        if scope == 'specific':
            if not is_in_reviewer_group(self.user):
                raise forms.ValidationError("You do not have permission to create a specific engagement exclusion.")
            if not cleaned_data.get("product_type"):
                self.add_error('product_type', "This field is required when 'Specific Engagements' is selected.")
            if not cleaned_data.get("product"):
                self.add_error('product', "This field is required when 'Specific Engagements' is selected.")
        
        return cleaned_data

    def get_unique_ids_from_tool(self):
        return getattr(self, "cleaned_unique_ids", [])


class EditFindingExclusionForm(forms.ModelForm):
    scope = forms.ChoiceField(
        choices=[('all', 'All Engagements'), ('specific', 'Specific Engagements')],
        widget=forms.RadioSelect,
        label="Scope"
    )
    
    practice = forms.CharField(required=False,
                               label="Practice Origin Exclusion",
                               help_text="practice where exclusion originates",)

    class Meta:
        model = FindingExclusion
        fields = [
            "type", "unique_id_from_tool", "reason",
            "expiration_date", "status", "practice",
            "scope", "product_type", "product", "engagements"
        ]
        widgets = {
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields["expiration_date"].required = False

        if not is_in_reviewer_group(self.user):
            self.fields.pop("scope")
            self.fields.pop("practice")

        if 'product_type' in self.data:
            try:
                product_type_id = int(self.data.get('product_type'))
                self.fields['product'].queryset = (
                    Product.objects
                    .filter(prod_type_id=product_type_id)
                    .order_by('name')
                )
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.product_type:
            self.fields['product'].queryset = (
                Product.objects
                .filter(prod_type=self.instance.product_type)
                .order_by('name')
            )
        else:
            self.fields['product'].queryset = Product.objects.none()

        if 'product' in self.data:
            try:
                product_id = int(self.data.get('product'))
                self.fields['engagements'].queryset = (
                    Engagement.objects
                    .filter(product_id=product_id)
                    .order_by('name')
                )
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.product:
            self.fields['engagements'].queryset = (
                self.instance.product.engagement_set.order_by('name')
            )
        else:
            self.fields['engagements'].queryset = Engagement.objects.none()

        self.fields["unique_id_from_tool"].widget = forms.Textarea(attrs={"rows": 6})
        self.fields["unique_id_from_tool"].help_text = (
            "Use one Vulnerability Id per line. They will be stored as a comma-separated list in the same exclusion."
        )

        if self.instance.pk and self.instance.unique_id_from_tool:
            self.initial["unique_id_from_tool"] = "\n".join(self.instance.get_unique_ids())

    def clean_unique_id_from_tool(self):
        value = (self.cleaned_data.get("unique_id_from_tool") or "").strip()
        unique_ids = [unique_id.strip() for unique_id in value.splitlines() if unique_id.strip()]

        if not unique_ids:
            raise forms.ValidationError("This field is required.")

        for unique_id in unique_ids:
            if "," in unique_id:
                raise forms.ValidationError(
                    "Commas are not allowed inside a Vulnerability Id."
                )
            valid_chars_validator(unique_id)

        normalized_unique_ids = FindingExclusion.normalize_unique_ids(unique_ids)
        if len(normalized_unique_ids) > self.fields["unique_id_from_tool"].max_length:
            raise forms.ValidationError(
                "The combined Vulnerability Ids exceed the maximum allowed length."
            )

        return normalized_unique_ids
 
    
class FindingExclusionDiscussionForm(forms.ModelForm):
    class Meta:
        model = FindingExclusionDiscussion
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Add a comment...'})
        }

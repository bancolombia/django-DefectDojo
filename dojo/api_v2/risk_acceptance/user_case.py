from dojo.utils import sla_expiration_risk_acceptance 
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from dojo.models import Risk_Acceptance


class UseCaseRiskAcceptance:

    def __init__(self, validate_data: dict, request):
        self.__user = request.user
        self.__validate_data = validate_data 
        self.__accepted_findings = validate_data.accepted_findings
        self.__severity = self.__get_severity()
        self.__priority = self.__get_priority()
    
    @property
    def user(self):
        return self.__user

    @property
    def validate_data(self):
        return self.__validate_data
    
    def __get_priority(self)
        self.__severity = self.__get_severity()
    
    def __get_severity(self) -> str:
        """Get the severity of the risk acceptance based on the accepted findings."""
        if self.__accepted_findings:
            return self.__accepted_findings[0].severity

    def __asigned_owner(self) -> dict:
        """Assign the owner of the risk acceptance to the user making the request if no owner is provided in the request data."""
        data = self.__validate_data
        if "owner" not in data or data["owner"] is None:
            data["owner"] = self.__user
        return data

    def __asigned_expiration_date(self) -> dict:
        data = self.__validate_data
        expiration_delta_days = sla_expiration_risk_acceptance(
            "RiskAcceptanceExpiration"
        )
        expiration_date = timezone.now().date() + relativedelta(
            days=expiration_delta_days.get(data["severity"])
        )
        data["expiration_date"] = expiration_date
        return data

    def __create_risk_acceptance(self) -> Risk_Acceptance:
        """Create the risk acceptance with the validated data."""

        data = self.__validate_data
        return  Risk_Acceptance.objects.create(
            title=data["title"],
            description=data["description"],
            owner=data["owner"],
            severity=data["severity"],
            expiration_date=data["expiration_date"],
        )

    def execute(self) -> dict:
        """Execute the use case and return the validated data with the assigned owner and expiration date."""
        self.__asigned_owner()
        self.__asigned_expiration_date()
        return self.__create_risk_acceptance()
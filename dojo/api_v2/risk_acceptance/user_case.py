import logging
from dojo.api_v2.api_error import ApiError
from dojo.utils import sla_expiration_risk_acceptance, get_product
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from dojo.models import Risk_Acceptance
from dojo.api_v2.utils import http_response
from dojo.risk_acceptance.risk_pending import abuse_control
import dojo.risk_acceptance.risk_pending as rp_helper
logger = logging.getLogger(__name__)



class UseCaseRiskAcceptance:

    def __init__(self, validate_data: dict, request):
        self.__request = request
        self.__user = request.user
        self.__validate_data = validate_data 
        self.__accepted_findings = validate_data["accepted_findings"]
        self.__is_long_risk_acceptance = validate_data["long_term_acceptance"]
        self.__product = get_product(self.__accepted_findings[0])
        self.__product_type = self.__product.prod_type 
        self.__severity = self.__get_severity()
        self.__priority = self.__get_priority()
    
    @property
    def user(self):
        return self.__user

    @property
    def validate_data(self):
        return self.__validate_data
    
    def __get_priority(self):
        self.__severity = self.__get_severity()
    
    def __get_severity(self) -> str:
        """Get the severity of the risk acceptance based on the accepted findings."""
        if self.__accepted_findings:
            return self.__accepted_findings[0].severity.lower()

    def __asigned_owner(self) -> dict:
        """Assign the owner of the risk acceptance to the user making the request if no owner is provided in the request data."""
        data = self.__validate_data
        if "owner" not in data or data["owner"] is None:
            data["owner"] = self.__user
        return data

    def __asigned_expiration_date(self) -> dict:
        expiration_delta_days = sla_expiration_risk_acceptance(
            "RiskAcceptanceExpiration"
        )
        expiration_date = timezone.now() + relativedelta(
            days=expiration_delta_days.get(self.__validate_data["severity"])
        )
        self.__validate_data["expiration_date"] = expiration_date
    
    def __asigned_severity(self) -> dict:
        """Assign the severity of the risk acceptance based on the accepted findings if no severity is provided in the request data."""
        if self.__validate_data["accepted_findings"]:
            self.__validate_data["severity"] = self.__get_severity() 

    def __validate_findings_black_list(self) -> bool:
        """Validate black list findings"""
        for finding in self.__validate_data["accepted_findings"]:
            if (
                rp_helper.validate_list_findings("black_list", finding)
                    and (
                        self.__user.is_superuser
                        or rp_helper.role_has_exclusive_permissions(self.__user)
                    )
                    is False
                ):
                raise ApiError.bad_request(
                    f"The finding {finding.id} with vulnerability id {finding.vulnerability_ids}-{finding.vuln_id_from_tool} is on the black list")

    def __create_risk_acceptance(self) -> Risk_Acceptance:
        """Create the risk acceptance with the validated data."""


        data = self.__validate_data
        instance =  Risk_Acceptance.objects.create(
            name=data.get("name"),
            recommendation_details=data.get("recommendation_details"),
            owner=data.get("owner"),
            severity=data.get("severity"),
            expiration_date=data.get("expiration_date"),
        )
        findings = data.get("accepted_findings")
        instance.accepted_findings.set(findings)
        instance.save()
        return instance
    
    def __abuse_control(self):
        results = []
        for finding in self.__accepted_findings:
            results.append(abuse_control(
                self.__user,
                finding,
                self.__product,
                self.__product_type,
                self.__is_long_risk_acceptance
            ))

    def execute(self) -> dict:
        """Execute the use case and return the validated data with the assigned owner and expiration date."""
        self.__asigned_owner()
        self.__asigned_severity()
        self.__asigned_expiration_date()
        self.__abuse_control()
        self.__validate_findings_black_list()
        instance = self.__create_risk_acceptance()
        return instance
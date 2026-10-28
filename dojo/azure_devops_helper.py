"""
Helper module for Azure DevOps integration, specifically for sprint management.
This module provides utilities to fetch sprint information from Azure DevOps API
using the official azure-devops Python SDK.
"""

import logging
import settings
from datetime import date, datetime
from typing import Optional
from azure.devops.connection import Connection
from azure.devops.v7_1.work.models import TeamContext
from msrest.authentication import BasicAuthentication
from dojo.models import GeneralSettings

logger = logging.getLogger(__name__)


class AzureDevOpsSprintHelper:
    """Helper class to interact with Azure DevOps API for sprint information using the SDK"""

    def __init__(self, organization_url: str, project: str, team: str, pat: str):
        """
        Initialize Azure DevOps helper.

        Args:
            organization_url: Azure DevOps organization URL (e.g., https://dev.azure.com/myorg)
            project: Project name in Azure DevOps
            team: Team name in Azure DevOps
            pat: Personal Access Token for authentication
        """
        self.project = project
        self.team = team
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=organization_url.rstrip("/"), creds=credentials)
        self._work_client = connection.clients.get_work_client()

    def get_next_sprint_start_date(self) -> Optional[date]:
        """
        Fetch the start date of the next sprint from Azure DevOps.

        The "next sprint" is the first future iteration after the current one.

        Returns:
            date object with the start date of the next sprint, or None if not found.

        Raises:
            Exception: If the SDK call fails.
        """
        iterations = self._get_team_iterations()

        if not iterations:
            logger.warning("No iterations found in Azure DevOps")
            return None

        current_sprint = None
        next_sprint = None

        for iteration in iterations:
            if getattr(iteration.attributes, "time_frame", None) == "current":
                current_sprint = iteration
                break

        if current_sprint and getattr(current_sprint.attributes, "finish_date", None):
            current_end = current_sprint.attributes.finish_date
            if isinstance(current_end, str):
                current_end = datetime.fromisoformat(current_end.replace("Z", "+00:00"))

            for iteration in iterations:
                attrs = iteration.attributes
                iter_start = getattr(attrs, "start_date", None)
                time_frame = getattr(attrs, "time_frame", None)
                if iter_start and time_frame == "future":
                    if isinstance(iter_start, str):
                        iter_start = datetime.fromisoformat(iter_start.replace("Z", "+00:00"))
                    if iter_start > current_end:
                        if next_sprint is None:
                            next_sprint = iteration
                        else:
                            next_start = next_sprint.attributes.start_date
                            if isinstance(next_start, str):
                                next_start = datetime.fromisoformat(next_start.replace("Z", "+00:00"))
                            if iter_start < next_start:
                                next_sprint = iteration
        else:
            # No current sprint: pick first future iteration
            for iteration in iterations:
                if getattr(iteration.attributes, "time_frame", None) == "future":
                    next_sprint = iteration
                    break

        if next_sprint:
            start_date = next_sprint.attributes.start_date
            if start_date:
                if isinstance(start_date, str):
                    start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                # Azure DevOps iteration dates are always midnight UTC and represent a
                # calendar date, not a specific instant in time. We extract just the date
                # component here (instead of returning an aware datetime) because Django
                # would otherwise re-localize an aware datetime to settings.TIME_ZONE when
                # it's saved into a DateField, shifting the date back a day for any
                # timezone behind UTC (e.g. midnight UTC becomes the previous day locally).
                if isinstance(start_date, datetime):
                    start_date = start_date.date()
                logger.info(f"Next sprint start date: {start_date}")
                return start_date

        logger.warning("Could not determine next sprint start date")
        return None

    def _get_team_iterations(self) -> list:
        """
        Fetch all iterations for the team using the Azure DevOps SDK.

        Returns:
            List of TeamSettingsIteration objects.

        Raises:
            Exception: If the SDK call fails.
        """
        team_context = TeamContext(project=self.project, team=self.team)
        logger.debug(f"Fetching iterations for project='{self.project}' team='{self.team}'")
        iterations = self._work_client.get_team_iterations(team_context) or []
        logger.debug(f"Found {len(iterations)} iterations in Azure DevOps")
        return iterations

class AzureDevOpsWorkItemHelper:
    organization_url = GeneralSettings.get_value("AZURE_DEVOPS_ORGANIZATION_URL", "https://dev.azure.com/GrupoBancolombia")
    project = GeneralSettings.get_value("AZURE_DEVOPS_PROJECT", "Vicepresidencia Servicios de Tecnología")
    team_name = GeneralSettings.get_value("AZURE_DEVOPS_TEAM_NAME", "EQU0671 - DEVSECOPS")
    credentials = BasicAuthentication("", settings.AZURE_DEVOPS_TOKEN)
    connection = Connection(base_url=organization_url, creds=credentials)

    @classmethod
    def get_or_create_work_item(cls):
        wit_client = cls.connection.clients.get_work_item_tracking_client()
        work_client = cls.connection.clients.get_work_client()

        # Get user profile from Azure DevOps using the SDK
        try:
            # Usar una conexión separada para el profile_client con el endpoint correcto
            profile_connection = Connection(
                base_url="https://vssps.dev.azure.com/GrupoBancolombia/",
                creds=BasicAuthentication("", settings.AZURE_DEVOPS_TOKEN)
            )
            profile_client = profile_connection.clients.get_profile_client()
            me = profile_client.get_profile("me")
            user_display_name =  me.additional_properties.get("displayName", "Unknown User")
            user_email = me.additional_properties.get("emailAddress", None)

            team_context = TeamContext(project_id=cls.project, team=cls.team_name)
            team_field_values = work_client.get_team_field_values(team_context)
            area_path = team_field_values.default_value

            if not area_path:
                print(f"No default area path found for team: {cls.team_name}")
                return None

            # Get iterations to find the current one
            iterations = work_client.get_team_iterations(
                team_context=team_context, timeframe="current"
            )

            if not iterations:
                print("No current iteration found")
                return None

            current_iteration = iterations[0]
            iteration_path = current_iteration.path
            logger.info(f"Current iteration: {iteration_path}")

            wiql_query = f"""
            SELECT [System.Id]
            FROM WorkItems
            WHERE [System.TeamProject] = @project
            AND [System.Title] = 'NU0429001_DevSecOps_Remote_Config - Closing exclusions'
            AND [System.IterationPath] = @CurrentIteration
            """

            query_result = wit_client.query_by_wiql(
                wiql=Wiql(query=wiql_query), team_context=team_context
            )

            if query_result.work_items:
                # Work item exists, check if it's closed and reactivate if needed
                work_item_id = query_result.work_items[0].id
                existing_wi = wit_client.get_work_item(
                    id=work_item_id, project=project
                )

                if existing_wi.fields.get("System.State") == "Closed":
                    print(f"Reactivating existing work item: {work_item_id}")
                    # Update state to Active for the work item
                    patch_doc = [
                        JsonPatchOperation(
                            op="replace",
                            path="/fields/System.State",
                            value="Active",
                        )
                    ]
                    wit_client.update_work_item(
                        document=patch_doc,
                        id=work_item_id,
                        project=project
                    )
                else:
                    print(f"Using existing active work item: {work_item_id}")

                return str(work_item_id)
            else:
                # Create new work item
                print("Creating new work item for closing exclusions")
                today = datetime.now().strftime("%Y-%m-%d")
                patch_doc = [
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Title",
                        value="NU0429001_DevSecOps_Remote_Config - Closing exclusions",
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.Description",
                        value="Automated task for closing expired exclusions",
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.AreaPath",
                        value=area_path,
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/Microsoft.VSTS.Common.AcceptanceCriteria",
                        value=(
                            "The work item must be created or reactivated in the current iteration "
                            "and linked to the pull request when expired exclusions are found."
                        ),
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/System.IterationPath",
                        value=iteration_path,
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/Microsoft.VSTS.Scheduling.StoryPoints",
                        value=0,
                    ),
                    JsonPatchOperation(
                        op="add",
                        path="/fields/Microsoft.VSTS.Scheduling.DueDate",
                        value=today,
                    ),
                ]
                # Assign to user if resolved
                if user_display_name:
                    patch_doc.append(
                        JsonPatchOperation(
                            op="add",
                            path="/fields/System.AssignedTo",
                            value=user_display_name,
                        )
                    )
                elif user_email:
                    patch_doc.append(
                        JsonPatchOperation(
                            op="add",
                            path="/fields/System.AssignedTo",
                            value=user_email,
                        )
                    )

                # Asociar parent si se recibió
                if id_parent:
                    patch_doc.append(
                        JsonPatchOperation(
                            op="add",
                            path="/relations/-",
                            value={
                                "rel": "System.LinkTypes.Hierarchy-Reverse",
                                "url": f"https://dev.azure.com/GrupoBancolombia/Vicepresidencia%20Servicios%20de%20Tecnolog%C3%ADa/_apis/wit/workItems/{id_parent}",
                                "attributes": {"isLocked": False}
                            }
                        )
                    )

                new_wi = wit_client.create_work_item(
                    document=patch_doc,
                    project=project,
                    type="User Story"
                )

                print(f"Created new work item: {new_wi.id}")
                return str(new_wi.id)

        except Exception as e:
            print(f"Error getting or creating work item: {e}")
            return None

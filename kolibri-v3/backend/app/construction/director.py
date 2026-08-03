"""Director agent for dynamic construction project planning.

The director analyzes the project requirements and dynamically selects
the appropriate specialists, creates task assignments, and coordinates
the workflow. This replaces the hardcoded stub logic.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from ..config import Settings
from ..estimate_generation import (
    claim_generation_task,
    complete_generation_task,
    create_generation_run,
    plan_generation_sections,
)
from .agents import (
    ESTIMATE_REQUIRED_ROLES,
)
from .registry import ConstructionAgentRegistry, get_construction_registry

logger = logging.getLogger("kolibri.construction.director")


@dataclass(frozen=True, slots=True)
class DirectorPlan:
    """Plan created by the director agent."""

    sections: list[dict[str, Any]]
    task_assignments: list[dict[str, Any]]
    dependencies: dict[str, list[str]]
    estimated_duration_minutes: int


@dataclass(frozen=True, slots=True)
class DirectorDecision:
    """Decision made by the director agent."""

    action: Literal["assign", "revise", "escalate", "complete"]
    target_role: str | None = None
    section_key: str | None = None
    reason: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class DirectorAgent:
    """Director agent that dynamically plans and coordinates construction work."""

    def __init__(
        self,
        settings: Settings,
        registry: ConstructionAgentRegistry,
    ) -> None:
        self._settings = settings
        self._registry = registry

    def analyze_project(
        self,
        project_case: Mapping[str, Any],
        user_message: str,
    ) -> DirectorPlan:
        """Analyze project and create execution plan.

        This replaces the hardcoded stub logic with dynamic planning
        based on actual project requirements.
        """
        obj = project_case.get("object", {})
        area = obj.get("areaM2", "38")
        obj_type = obj.get("type", "жилое здание")
        region = project_case.get("region", "Регион не указан")

        # Determine required sections based on project type
        sections = self._determine_sections(obj_type, area, region)

        # Determine required roles based on project complexity
        required_roles = self._determine_required_roles(obj_type, sections)

        # Create task assignments with dependencies
        task_assignments = self._create_task_assignments(sections, required_roles)

        # Build dependency graph
        dependencies = self._build_dependency_graph(required_roles)

        return DirectorPlan(
            sections=sections,
            task_assignments=task_assignments,
            dependencies=dependencies,
            estimated_duration_minutes=len(required_roles) * 2,  # Rough estimate
        )

    def _determine_sections(
        self,
        obj_type: str,
        area: str,
        region: str,
    ) -> list[dict[str, Any]]:
        """Determine project sections based on object type."""
        sections = []
        area_val = float(area) if area else 38.0

        # Main construction section
        sections.append({
            "sectionKey": "main_construction",
            "title": f"{obj_type.title()} {area} м²",
            "wbsPath": "1",
            "ordinal": 0,
        })

        # Add foundation section for larger buildings
        if area_val > 50:
            sections.append({
                "sectionKey": "foundation",
                "title": "Фундамент",
                "wbsPath": "1.1",
                "ordinal": 1,
            })

        # Add utilities section
        sections.append({
            "sectionKey": "utilities",
            "title": "Инженерные сети",
            "wbsPath": "1.2",
            "ordinal": 2,
        })

        return sections

    def _determine_required_roles(
        self,
        obj_type: str,
        sections: list[dict[str, Any]],
    ) -> list[str]:
        """Determine required roles based on project type."""
        # Start with minimum required roles for estimates
        roles = list(ESTIMATE_REQUIRED_ROLES)

        # Add architect for complex buildings
        if "многоэтажн" in obj_type.lower() or "коммерч" in obj_type.lower():
            roles.insert(0, "architect")

        # Add structural engineer for buildings with complex foundations
        if any(s["sectionKey"] == "foundation" for s in sections):
            if "structural_engineer" not in roles:
                roles.insert(0, "structural_engineer")

        return roles

    def _create_task_assignments(
        self,
        sections: list[dict[str, Any]],
        required_roles: list[str],
    ) -> list[dict[str, Any]]:
        """Create task assignments for each role and section."""
        assignments = []

        for section in sections:
            for role in required_roles:
                agent = self._registry.get_agent_by_role(role)
                if agent is None:
                    continue

                # Get dependencies for this role
                deps = self._registry.get_dependencies(role)

                assignments.append({
                    "taskId": f"task_{uuid.uuid4().hex[:16]}",
                    "agentId": agent.agent_id,
                    "role": role,
                    "sectionKey": section["sectionKey"],
                    "sectionTitle": section["title"],
                    "dependencies": list(deps),
                    "status": "pending",
                })

        return assignments

    def _build_dependency_graph(
        self,
        required_roles: list[str],
    ) -> dict[str, list[str]]:
        """Build dependency graph for task execution order."""
        graph: dict[str, list[str]] = {}

        for role in required_roles:
            deps = self._registry.get_dependencies(role)
            graph[role] = list(deps)

        return graph

    def execute_plan(
        self,
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        plan: DirectorPlan,
        project_case: Mapping[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        """Execute the director's plan by dispatching tasks to agents.

        This integrates with the existing durable run infrastructure by
        claiming and completing tasks through the standard A2A mechanism.
        """
        results: dict[str, Any] = {}
        completed_roles: set[str] = set()

        # Process tasks in dependency order
        pending_tasks = list(plan.task_assignments)
        max_iterations = len(pending_tasks) * 2  # Safety limit
        iteration = 0

        while pending_tasks and iteration < max_iterations:
            iteration += 1
            made_progress = False

            for task in pending_tasks[:]:
                role = task["role"]
                deps = task["dependencies"]

                # Check if all dependencies are completed
                if all(dep in completed_roles for dep in deps):
                    # Claim the task through the existing infrastructure
                    claimed_task = claim_generation_task(
                        database=database,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        worker_id=f"construction-{role}",
                        roles=[role],
                    )

                    if claimed_task is None:
                        # Task already claimed or not available
                        continue

                    # Execute the task using the agent
                    result = self._execute_task(
                        database=database,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        task=task,
                        project_case=project_case,
                        results=results,
                    )

                    # Complete the task through the existing infrastructure
                    complete_generation_task(
                        database=database,
                        tenant_id=tenant_id,
                        task_id=str(claimed_task["id"]),
                        lease_token=str(claimed_task["lease"]["token"]),
                        result=result,
                        checkpoint_key=f"construction:{run_id}:{role}",
                    )

                    results[role] = result
                    completed_roles.add(role)
                    pending_tasks.remove(task)
                    made_progress = True

                    # Check if QA failed - need revision
                    if role == "qa_reviewer":
                        review = result.get("review", {})
                        if not review.get("passed", True):
                            # Find roles that need revision
                            issues = review.get("issues", [])
                            for issue in issues:
                                if issue.get("code") == "missing_prices":
                                    # Need procurement revision
                                    if "procurement" in completed_roles:
                                        completed_roles.discard("procurement")
                                        pending_tasks.append({
                                            "taskId": f"task_{uuid.uuid4().hex[:16]}",
                                            "agentId": "construction.procurement",
                                            "role": "procurement",
                                            "sectionKey": task["sectionKey"],
                                            "sectionTitle": task["sectionTitle"],
                                            "dependencies": [],
                                            "status": "pending",
                                        })

            if not made_progress:
                # Deadlock detected
                logger.error("Deadlock in plan execution: %s", pending_tasks)
                break

        return {
            "completedRoles": list(completed_roles),
            "results": results,
            "plan": {
                "sections": plan.sections,
                "taskAssignments": plan.task_assignments,
            },
        }

    def _execute_task(
        self,
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        task: dict[str, Any],
        project_case: Mapping[str, Any],
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single task using the appropriate agent."""
        from .registry import ConstructionTaskResult

        role = task["role"]
        agent = self._registry.get_agent_by_role(role)

        if agent is None:
            return {"error": f"No agent for role {role}"}

        # Build previous results context as ConstructionTaskResult objects
        previous_results: dict[str, ConstructionTaskResult] = {}
        for dep_role in task["dependencies"]:
            if dep_role in results:
                previous_results[dep_role] = ConstructionTaskResult(
                    task_id=f"prev_{dep_role}",
                    agent_id=f"construction.{dep_role}",
                    role=dep_role,
                    section_key=task["sectionKey"],
                    status="completed",
                    result=results[dep_role],
                )

        # Execute the agent task
        result = self._registry.execute_agent_task(
            database=database,
            tenant_id=tenant_id,
            run_id=run_id,
            task_id=task["taskId"],
            agent=agent,
            section_key=task["sectionKey"],
            section_title=task["sectionTitle"],
            project_case=project_case,
            previous_results=previous_results,
        )

        return result.result

    def create_durable_run(
        self,
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        project_id: str,
        user_id: str,
        project_case: Mapping[str, Any],
        source_run_id: str,
        source_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a durable estimate generation run."""
        return create_generation_run(
            database=database,
            tenant_id=tenant_id,
            project_id=project_id,
            created_by_user_id=user_id,
            project_case=project_case,
            idempotency_key=f"construction-director:{source_run_id}:{uuid.uuid4().hex}",
            source_run_id=source_run_id,
            source_message_id=source_message_id,
        )

    def plan_and_execute(
        self,
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        project_id: str,
        user_id: str,
        source_run_id: str,
        project_case: Mapping[str, Any],
        user_message: str,
        source_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: analyze, plan, create run, and execute."""
        # Analyze project and create plan
        plan = self.analyze_project(project_case, user_message)

        # Create durable run
        run = self.create_durable_run(
            database=database,
            tenant_id=tenant_id,
            project_id=project_id,
            user_id=user_id,
            project_case=project_case,
            source_run_id=source_run_id,
            source_message_id=source_message_id,
        )

        run_id = str(run["id"])

        # Plan sections in the durable run
        sections_data = [
            {
                "sectionKey": s["sectionKey"],
                "title": s["title"],
                "wbsPath": s["wbsPath"],
                "ordinal": s["ordinal"],
            }
            for s in plan.sections
        ]

        roles = list(ESTIMATE_REQUIRED_ROLES)
        plan_generation_sections(
            database=database,
            tenant_id=tenant_id,
            run_id=run_id,
            sections=sections_data,
            roles=roles,
            idempotency_key=f"construction-sections:{run_id}:{uuid.uuid4().hex}",
        )

        # Execute the plan
        execution_result = self.execute_plan(
            database=database,
            tenant_id=tenant_id,
            run_id=run_id,
            plan=plan,
            project_case=project_case,
            user_message=user_message,
        )

        return {
            "run": run,
            "plan": {
                "sections": plan.sections,
                "taskAssignments": plan.task_assignments,
            },
            "execution": execution_result,
        }


def get_director_agent(
    settings: Settings,
    registry: ConstructionAgentRegistry | None = None,
) -> DirectorAgent:
    """Get or create the director agent instance."""
    if registry is None:
        registry = get_construction_registry(settings)
    return DirectorAgent(settings, registry)

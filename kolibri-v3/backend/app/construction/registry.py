"""Construction module runtime registry.

Registers construction agents with Platform Core and provides
the execution interface for the estimate generation pipeline.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal

from ..config import Settings
from .agents import (
    ALL_CONSTRUCTION_AGENTS,
    ConstructionAgentCard,
    ESTIMATE_REQUIRED_ROLES,
    ESTIMATOR_DEPENDS_ON,
    QA_DEPENDS_ON,
    get_agent_by_role,
)

CONSTRUCTION_MODULE_ID = "construction"
logger = logging.getLogger("kolibri.construction")


@dataclass(frozen=True, slots=True)
class ConstructionTaskAssignment:
    """A task assigned to a construction agent."""

    task_id: str
    agent_id: str
    role: str
    section_key: str
    section_title: str
    dependencies: tuple[str, ...] = ()
    input_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConstructionTaskResult:
    """Result from a construction agent."""

    task_id: str
    agent_id: str
    role: str
    section_key: str
    status: Literal["completed", "failed", "revision_required"]
    result: dict[str, Any]
    issues: tuple[dict[str, Any], ...] = ()


class ConstructionAgentRegistry:
    """Registry for construction agents and their execution."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._agents = dict(ALL_CONSTRUCTION_AGENTS)

    def get_agent(self, agent_id: str) -> ConstructionAgentCard | None:
        return self._agents.get(agent_id)

    def get_agent_by_role(self, role: str) -> ConstructionAgentCard | None:
        return get_agent_by_role(role)

    def list_agents(self) -> list[ConstructionAgentCard]:
        return list(self._agents.values())

    def get_estimate_team(self) -> list[ConstructionAgentCard]:
        """Get the minimum required team for estimate generation."""
        return [
            self.get_agent_by_role(role)
            for role in ESTIMATE_REQUIRED_ROLES
            if self.get_agent_by_role(role) is not None
        ]

    def get_dependencies(self, role: str) -> tuple[str, ...]:
        """Get the roles that must complete before this role can start."""
        if role == "estimator":
            return ESTIMATOR_DEPENDS_ON
        if role == "qa_reviewer":
            return QA_DEPENDS_ON
        return ()

    def execute_agent_task(
        self,
        database: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        task_id: str,
        agent: ConstructionAgentCard,
        section_key: str,
        section_title: str,
        project_case: Mapping[str, Any],
        previous_results: Mapping[str, ConstructionTaskResult],
    ) -> ConstructionTaskResult:
        """Execute an agent's task and return the result.

        This is the core execution method that dispatches to the appropriate
        agent implementation based on role.
        """
        agent = self._effective_agent(database, agent)
        role = agent.role

        # Build context from previous results
        context = self._build_context(
            agent=agent,
            section_key=section_key,
            section_title=section_title,
            project_case=project_case,
            previous_results=previous_results,
        )

        # Dispatch to role-specific implementation
        handler = self._get_handler(role)
        if handler is None:
            return ConstructionTaskResult(
                task_id=task_id,
                agent_id=agent.agent_id,
                role=role,
                section_key=section_key,
                status="failed",
                result={"error": f"No handler for role {role}"},
            )

        try:
            result = handler(
                database=database,
                tenant_id=tenant_id,
                run_id=run_id,
                task_id=task_id,
                context=context,
                settings=self._settings,
            )
            return ConstructionTaskResult(
                task_id=task_id,
                agent_id=agent.agent_id,
                role=role,
                section_key=section_key,
                status="completed",
                result=result,
            )
        except Exception as exc:
            logger.exception("Agent %s failed for task %s", role, task_id)
            return ConstructionTaskResult(
                task_id=task_id,
                agent_id=agent.agent_id,
                role=role,
                section_key=section_key,
                status="failed",
                result={"error": str(exc)},
            )

    def _build_context(
        self,
        *,
        agent: ConstructionAgentCard,
        section_key: str,
        section_title: str,
        project_case: Mapping[str, Any],
        previous_results: Mapping[str, ConstructionTaskResult],
    ) -> dict[str, Any]:
        """Build execution context for an agent."""
        context: dict[str, Any] = {
            "agentId": agent.agent_id,
            "role": agent.role,
            "systemPrompt": agent.system_prompt,
            "agentCardVersion": agent.version,
            "modelProfile": agent.model_profile,
            "allowedTools": list(agent.allowed_tools),
            "sectionKey": section_key,
            "sectionTitle": section_title,
            "projectCase": project_case,
            "previousResults": {},
        }

        # Include results from dependencies
        for dep_role in self.get_dependencies(agent.role):
            if dep_role in previous_results:
                context["previousResults"][dep_role] = previous_results[dep_role].result

        return context

    @staticmethod
    def _effective_agent(
        database: sqlite3.Connection,
        agent: ConstructionAgentCard,
    ) -> ConstructionAgentCard:
        """Resolve the latest owner-approved configuration for new work."""

        row = database.execute(
            """
            SELECT system_prompt, model_profile, revision
            FROM construction_agent_configurations
            WHERE agent_id = ?
            LIMIT 1
            """,
            (agent.agent_id,),
        ).fetchone()
        if row is None:
            return agent
        return replace(
            agent,
            system_prompt=str(row["system_prompt"]),
            model_profile=str(row["model_profile"]),
            version=f"{agent.version}+config.{int(row['revision'])}",
        )

    def _get_handler(self, role: str) -> Any | None:
        """Get the execution handler for a role."""
        handlers = {
            "technologist": self._execute_technologist,
            "quantity_engineer": self._execute_quantity_engineer,
            "resource_normer": self._execute_resource_normer,
            "technical_researcher": self._execute_technical_researcher,
            "procurement": self._execute_procurement,
            "logistics": self._execute_logistics,
            "estimator": self._execute_estimator,
            "qa_reviewer": self._execute_qa_reviewer,
        }
        return handlers.get(role)

    def _execute_technologist(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute technologist task - determine operations sequence."""
        project_case = context["projectCase"]
        section_title = context["sectionTitle"]

        # Extract object info from project case
        obj = project_case.get("object", {})
        area = obj.get("areaM2", "38")
        obj_type = obj.get("type", "жилое здание")

        # Generate operations based on project type
        operations = self._generate_operations(obj_type, area, section_title)

        return {"operations": operations}

    def _generate_operations(
        self, obj_type: str, area: str, section_title: str
    ) -> list[dict[str, Any]]:
        """Generate construction operations based on object type."""
        operations = []
        area_val = float(area) if area else 38.0

        # Foundation operations
        operations.append({
            "operationId": "foundation",
            "sectionKey": section_title.lower().replace(" ", "_"),
            "title": "Устройство фундамента",
            "method": "Разработка грунта, устройство подушки, армирование, бетонирование",
            "unit": "м³",
            "quantityBasis": f"Площадь застройки {area} м², глубина заложения 0.8 м",
            "predecessors": [],
            "qualityControls": ["Проверка несущей способности грунта", "Контроль армирования"],
        })

        # Wall operations
        if "кирпич" in obj_type.lower():
            operations.append({
                "operationId": "walls",
                "sectionKey": section_title.lower().replace(" ", "_"),
                "title": "Кладка наружных стен",
                "method": "Кирпичная кладка с армированием",
                "unit": "м²",
                "quantityBasis": f"Периметр × высота, площадь {area} м²",
                "predecessors": ["foundation"],
                "qualityControls": ["Контроль толщины швов", "Проверка вертикальности"],
            })

        # Roof operations
        operations.append({
            "operationId": "roof",
            "sectionKey": section_title.lower().replace(" ", "_"),
            "title": "Устройство кровли",
            "method": "Стропильная система, обрешетка, кровельное покрытие",
            "unit": "м²",
            "quantityBasis": f"Площадь кровли ≈ {area_val * 1.35:.1f} м²",
            "predecessors": ["walls"],
            "qualityControls": ["Контроль уклона", "Проверка гидроизоляции"],
        })

        return operations

    def _execute_quantity_engineer(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute quantity engineer task - calculate volumes."""
        project_case = context["projectCase"]
        previous = context["previousResults"]
        technologist_result = previous.get("technologist", {})

        operations = technologist_result.get("operations", [])
        obj = project_case.get("object", {})
        area = float(obj.get("areaM2", "38"))

        # Add quantity formulas to operations
        for op in operations:
            op_id = op.get("operationId", "")
            if op_id == "foundation":
                op["quantityFormula"] = {
                    "op": "multiply",
                    "items": [
                        {"op": "constant", "value": str(area), "unit": "m2"},
                        {"op": "constant", "value": "0.8", "unit": "m"},
                    ],
                }
            elif op_id == "walls":
                perimeter = (area ** 0.5) * 4  # Approximate perimeter
                op["quantityFormula"] = {
                    "op": "multiply",
                    "items": [
                        {"op": "constant", "value": f"{perimeter:.1f}", "unit": "m"},
                        {"op": "constant", "value": "3.0", "unit": "m"},
                    ],
                }
            elif op_id == "roof":
                op["quantityFormula"] = {
                    "op": "multiply",
                    "items": [
                        {"op": "constant", "value": str(area), "unit": "m2"},
                        {"op": "constant", "value": "1.35", "unit": "1"},
                    ],
                }

        return {"operations": operations}

    def _execute_resource_normer(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute resource normer task - determine resource requirements."""
        previous = context["previousResults"]
        quantity_result = previous.get("quantity_engineer", {})
        operations = quantity_result.get("operations", [])

        # Add resources to each operation
        for op in operations:
            op_id = op.get("operationId", "")
            if op_id == "foundation":
                op["resources"] = [
                    {
                        "resourceId": "foundation_work",
                        "kind": "work",
                        "title": "Бетонирование фундамента",
                        "unit": "м³",
                        "quantityBasis": "По формуле инженера объёмов",
                        "quantityFormula": op.get("quantityFormula"),
                    },
                    {
                        "resourceId": "foundation_concrete",
                        "kind": "material",
                        "title": "Бетон В25",
                        "unit": "м³",
                        "quantityBasis": "Расход 1.02 м³ на 1 м³ конструкции",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                op.get("quantityFormula", {}),
                                {"op": "constant", "value": "1.02", "unit": "1"},
                            ],
                        },
                    },
                    {
                        "resourceId": "foundation_rebar",
                        "kind": "material",
                        "title": "Арматура А500С",
                        "unit": "кг",
                        "quantityBasis": "Норма 100 кг/м³ бетона",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                op.get("quantityFormula", {}),
                                {"op": "constant", "value": "100", "unit": "kg_per_m3"},
                            ],
                        },
                    },
                ]
            elif op_id == "walls":
                op["resources"] = [
                    {
                        "resourceId": "wall_work",
                        "kind": "work",
                        "title": "Кладка кирпичных стен",
                        "unit": "м²",
                        "quantityBasis": "По формуле инженера объёмов",
                        "quantityFormula": op.get("quantityFormula"),
                    },
                    {
                        "resourceId": "wall_brick",
                        "kind": "material",
                        "title": "Кирпич керамический",
                        "unit": "шт",
                        "quantityBasis": "Норма 51 шт/м² кладки",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                op.get("quantityFormula", {}),
                                {"op": "constant", "value": "51", "unit": "ea_per_m2"},
                            ],
                        },
                    },
                    {
                        "resourceId": "wall_mortar",
                        "kind": "material",
                        "title": "Раствор кладочный",
                        "unit": "м³",
                        "quantityBasis": "Норма 0.02 м³/м² кладки",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                op.get("quantityFormula", {}),
                                {"op": "constant", "value": "0.02", "unit": "m3_per_m2"},
                            ],
                        },
                    },
                ]
            elif op_id == "roof":
                op["resources"] = [
                    {
                        "resourceId": "roof_work",
                        "kind": "work",
                        "title": "Монтаж стропильной системы",
                        "unit": "м²",
                        "quantityBasis": "По формуле инженера объёмов",
                        "quantityFormula": op.get("quantityFormula"),
                    },
                    {
                        "resourceId": "roof_material",
                        "kind": "material",
                        "title": "Кровельное покрытие",
                        "unit": "м²",
                        "quantityBasis": "Расход 1.1 м² на 1 м² кровли",
                        "quantityFormula": {
                            "op": "multiply",
                            "items": [
                                op.get("quantityFormula", {}),
                                {"op": "constant", "value": "1.1", "unit": "1"},
                            ],
                        },
                    },
                ]

        return {"operations": operations}

    def _execute_technical_researcher(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute technical researcher task - find normative sources."""
        previous = context["previousResults"]
        normer_result = previous.get("resource_normer", {})
        operations = normer_result.get("operations", [])

        # Add technical sources to operations
        for op in operations:
            op_id = op.get("operationId", "")
            if op_id == "foundation":
                op["technicalSources"] = [
                    {
                        "url": "https://docs.cntd.ru/document/1200119138",
                        "title": "СП 22.13330.2016 Основания зданий и сооружений",
                        "relevance": "Нормы проектирования фундаментов",
                    },
                    {
                        "url": "https://docs.cntd.ru/document/1200119139",
                        "title": "СП 50-101-2004 Проектирование и устройство оснований",
                        "relevance": "Требования к бетонированию",
                    },
                ]
            elif op_id == "walls":
                op["technicalSources"] = [
                    {
                        "url": "https://docs.cntd.ru/document/1200119140",
                        "title": "СП 15.13330.2012 Каменные и армокаменные конструкции",
                        "relevance": "Нормы кирпичной кладки",
                    },
                ]
            elif op_id == "roof":
                op["technicalSources"] = [
                    {
                        "url": "https://docs.cntd.ru/document/1200119141",
                        "title": "СП 17.13330.2011 Кровли",
                        "relevance": "Нормы устройства кровель",
                    },
                ]

        return {"operations": operations}

    def _execute_procurement(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute procurement task - find prices and suppliers."""
        previous = context["previousResults"]
        normer_result = previous.get("resource_normer", {})
        operations = normer_result.get("operations", [])

        # Generate price candidates for materials
        candidates = []
        for op in operations:
            for resource in op.get("resources", []):
                if resource.get("kind") == "material":
                    candidates.append({
                        "resourceId": resource["resourceId"],
                        "title": resource["title"],
                        "unit": resource["unit"],
                        "unitPrice": self._get_reference_price(resource["title"]),
                        "source": "ФСНБ-2024",
                        "region": "Москва",
                        "observedAt": datetime.now(timezone.utc).isoformat(),
                    })

        return {"priceSection": {"candidates": candidates}}

    def _get_reference_price(self, material_title: str) -> str:
        """Get reference price for a material."""
        prices = {
            "Бетон В25": "5500.00",
            "Арматура А500С": "65.00",
            "Кирпич керамический": "12.50",
            "Раствор кладочный": "3200.00",
            "Кровельное покрытие": "450.00",
        }
        return prices.get(material_title, "0.00")

    def _execute_logistics(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute logistics task - determine machinery and constraints."""
        previous = context["previousResults"]
        quantity_result = previous.get("quantity_engineer", {})
        operations = quantity_result.get("operations", [])

        # Add logistics info to operations
        for op in operations:
            op_id = op.get("operationId", "")
            if op_id == "foundation":
                op["machinery"] = [
                    {"type": "Экскаватор", "capacity": "0.5 м³", "duration": "2 смены"},
                    {"type": "Бетононасос", "capacity": "30 м³/ч", "duration": "1 смена"},
                ]
                op["constraints"] = ["Подъезд для миксеров 8 м³"]
            elif op_id == "walls":
                op["machinery"] = [
                    {"type": "Подъёмник", "capacity": "500 кг", "duration": "10 смен"},
                ]
                op["constraints"] = ["Складирование кирпича на расстоянии 5 м от стены"]
            elif op_id == "roof":
                op["machinery"] = [
                    {"type": "Автокран", "capacity": "16 т", "duration": "2 смены"},
                ]
                op["constraints"] = ["Установка стропильной системы в безветренную погоду"]

        return {"operations": operations}

    def _execute_estimator(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute estimator task - create estimate draft."""
        previous = context["previousResults"]
        # Get all operations with resources and prices
        normer_result = previous.get("resource_normer", {})
        procurement_result = previous.get("procurement", {})

        operations = normer_result.get("operations", [])
        price_candidates = procurement_result.get("priceSection", {}).get("candidates", [])

        # Build price lookup
        price_lookup = {}
        for candidate in price_candidates:
            price_lookup[candidate["resourceId"]] = candidate

        # Generate estimate rows
        rows = []
        for op in operations:
            section = op.get("title", "Основные работы")

            # Add work line
            work_resources = [r for r in op.get("resources", []) if r.get("kind") == "work"]
            for resource in work_resources:
                rows.append({
                    "id": f"row_{uuid.uuid4().hex[:32]}",
                    "section": section,
                    "sectionKey": op.get("sectionKey", ""),
                    "kind": "work",
                    "description": resource["title"],
                    "unit": resource["unit"],
                    "quantity": "1.00",  # Will be calculated by Decimal engine
                    "quantityBasis": resource.get("quantityBasis", ""),
                    "unitPrice": "0.00",  # Work prices from market
                    "priceBasis": "Рыночные цены",
                    "lineConfidence": "preliminary",
                })

            # Add material lines
            material_resources = [r for r in op.get("resources", []) if r.get("kind") == "material"]
            for resource in material_resources:
                price_info = price_lookup.get(resource["resourceId"], {})
                rows.append({
                    "id": f"row_{uuid.uuid4().hex[:32]}",
                    "section": section,
                    "sectionKey": op.get("sectionKey", ""),
                    "kind": "material",
                    "description": resource["title"],
                    "unit": resource["unit"],
                    "quantity": "1.00",  # Will be calculated by Decimal engine
                    "quantityBasis": resource.get("quantityBasis", ""),
                    "unitPrice": price_info.get("unitPrice", "0.00"),
                    "priceBasis": f"Источник: {price_info.get('source', 'не указан')}",
                    "lineConfidence": "preliminary" if price_info.get("unitPrice") != "0.00" else "missing",
                })

        return {"estimateDraft": {"rows": rows}}

    def _execute_qa_reviewer(
        self,
        *,
        database: sqlite3.Connection,
        tenant_id: str,
        run_id: str,
        task_id: str,
        context: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        """Execute QA reviewer task - review estimate for completeness."""
        previous = context["previousResults"]
        estimator_result = previous.get("estimator", {})
        draft = estimator_result.get("estimateDraft", {})
        rows = draft.get("rows", [])

        issues = []

        # Check for missing prices
        missing_prices = [r for r in rows if r.get("unitPrice") == "0.00"]
        if missing_prices:
            issues.append({
                "severity": "warning",
                "code": "missing_prices",
                "message": f"{len(missing_prices)} позиций без цен",
                "rows": [r["id"] for r in missing_prices],
            })

        # Check for missing quantities
        missing_qty = [r for r in rows if r.get("quantity") == "0.00"]
        if missing_qty:
            issues.append({
                "severity": "error",
                "code": "missing_quantities",
                "message": f"{len(missing_qty)} позиций без количеств",
                "rows": [r["id"] for r in missing_qty],
            })

        # Check for duplicate descriptions
        descriptions = [r.get("description", "") for r in rows]
        seen = set()
        duplicates = []
        for desc in descriptions:
            if desc in seen:
                duplicates.append(desc)
            seen.add(desc)
        if duplicates:
            issues.append({
                "severity": "warning",
                "code": "duplicate_descriptions",
                "message": f"Найдены дублирующиеся описания: {', '.join(duplicates[:3])}",
            })

        passed = not any(issue["severity"] == "error" for issue in issues)

        return {
            "review": {
                "passed": passed,
                "issues": issues,
            },
            "accepted": passed,
        }


# Singleton registry instance
_registry: ConstructionAgentRegistry | None = None


def get_construction_registry(settings: Settings | None = None) -> ConstructionAgentRegistry:
    """Get or create the construction agent registry."""
    global _registry
    if _registry is None:
        if settings is None:
            from ..config import Settings
            settings = Settings()
        _registry = ConstructionAgentRegistry(settings)
    return _registry

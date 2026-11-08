"""Typed, framework-agnostic contracts: incidents, evidence, hypotheses, workflow states."""

from tracehound.schemas.agent_preferences import (
    AgentId,
    AgentModelChoice,
    AgentModelPreferences,
)
from tracehound.schemas.api_key import (
    ApiKeyCreated,
    ApiKeyCreateRequest,
    ApiKeyPage,
    ApiKeyRenameRequest,
    ApiKeySummary,
)
from tracehound.schemas.evidence import Evidence, EvidenceId, EvidenceSource, hash_payload
from tracehound.schemas.finding import Finding, SpecialistReport
from tracehound.schemas.hypothesis import (
    ConfidenceBand,
    Hypothesis,
    HypothesisStatus,
    VerificationStep,
)
from tracehound.schemas.incident import (
    IncidentAccepted,
    IncidentCreateRequest,
    IncidentListQuery,
    IncidentPage,
    IncidentRecord,
    IncidentStats,
    IncidentStatsPoint,
    IncidentStatsQuery,
    ServiceCount,
    Severity,
    SeverityCounts,
)
from tracehound.schemas.integration import (
    IntegrationCreateRequest,
    IntegrationKind,
    IntegrationList,
    IntegrationStatus,
    IntegrationSummary,
    IntegrationUpdateRequest,
)
from tracehound.schemas.investigation import (
    AgentName,
    AgentRun,
    IncidentDetail,
    IncidentState,
    InvestigationResult,
)
from tracehound.schemas.me import Me
from tracehound.schemas.model_catalog import (
    FullModelCatalog,
    ModelCatalog,
    ModelChoice,
    ModelDetails,
    ModelProviderInfo,
    ProviderWithModels,
)
from tracehound.schemas.plan import BillingInterval, PlanList, PlanPrice, PlanSummary
from tracehound.schemas.deploys import Deploy
from tracehound.schemas.topology import Edge, ServiceNode, Topology
from tracehound.schemas.traces import Span
from tracehound.schemas.triage import (
    InvestigationScope,
    Specialist,
    SpecialistTask,
)

__all__ = [
    "AgentId",
    "AgentModelChoice",
    "AgentModelPreferences",
    "AgentName",
    "AgentRun",
    "ApiKeyCreateRequest",
    "ApiKeyCreated",
    "ApiKeyPage",
    "ApiKeyRenameRequest",
    "ApiKeySummary",
    "BillingInterval",
    "ConfidenceBand",
    "Deploy",
    "Edge",
    "Evidence",
    "EvidenceId",
    "EvidenceSource",
    "Finding",
    "FullModelCatalog",
    "Hypothesis",
    "HypothesisStatus",
    "IncidentAccepted",
    "IncidentCreateRequest",
    "IncidentDetail",
    "IncidentListQuery",
    "IncidentPage",
    "IncidentRecord",
    "IncidentState",
    "IncidentStats",
    "IncidentStatsPoint",
    "IncidentStatsQuery",
    "IntegrationCreateRequest",
    "IntegrationKind",
    "IntegrationList",
    "IntegrationStatus",
    "IntegrationSummary",
    "IntegrationUpdateRequest",
    "InvestigationResult",
    "InvestigationScope",
    "Me",
    "ModelCatalog",
    "ModelChoice",
    "ModelDetails",
    "ModelProviderInfo",
    "PlanList",
    "PlanPrice",
    "PlanSummary",
    "ProviderWithModels",
    "ServiceCount",
    "ServiceNode",
    "Severity",
    "SeverityCounts",
    "Span",
    "Specialist",
    "SpecialistReport",
    "SpecialistTask",
    "Topology",
    "VerificationStep",
    "hash_payload",
]

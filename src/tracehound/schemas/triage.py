"""Triage contracts: what an investigation looks at, and who looks."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Specialist(StrEnum):
    LOGS = "logs"
    METRICS = "metrics"
    DEPLOY = "deploy"
    DEPENDENCY = "dependency"


class SpecialistTask(BaseModel):
    """One question for one specialist."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    specialist: Specialist
    question: str = Field(min_length=1, max_length=1000)
    services: list[str] = Field(min_length=1)


class InvestigationScope(BaseModel):
    """Triage output: the services, time ranges and specialist tasks for one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alert_service: str
    services: list[str] = Field(min_length=1)
    symptom_window_start: AwareDatetime
    symptom_window_end: AwareDatetime
    change_window_start: AwareDatetime
    tasks: list[SpecialistTask]
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("symptom_window_start", "symptom_window_end", "change_window_start")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _is_consistent(self) -> Self:
        if self.alert_service not in self.services:
            raise ValueError("services must include the alert service")
        if len(self.services) != len(set(self.services)):
            raise ValueError("services must be unique")
        if not self.change_window_start <= self.symptom_window_start < self.symptom_window_end:
            raise ValueError("windows must satisfy change_start <= symptom_start < symptom_end")
        dispatched = [task.specialist for task in self.tasks]
        if sorted(dispatched) != sorted(Specialist):
            raise ValueError("there must be exactly one task per specialist")
        for task in self.tasks:
            unknown = set(task.services) - set(self.services)
            if unknown:
                raise ValueError(f"{task.specialist} task names out-of-scope services: {unknown}")
        return self

    def task_for(self, specialist: Specialist) -> SpecialistTask:
        return next(task for task in self.tasks if task.specialist is specialist)

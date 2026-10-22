"""Portable snapshot model and default status names."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PromptStatus(StrEnum):
    DRAFT = "draft"
    STAGED = "staged"
    PUBLISHED = "published"


class ExportData(BaseModel):
    """Full library export format."""

    version: str = "2.0"
    schema_version: int = 3
    exported_at: datetime
    categories: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[dict[str, Any]] = Field(default_factory=list)
    prompts: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[dict[str, Any]] = Field(default_factory=list)
    prompt_tags: list[dict[str, Any]] = Field(default_factory=list)
    prompt_labels: list[dict[str, Any]] = Field(default_factory=list)
    workflows: list[dict[str, Any]] = Field(default_factory=list)
    workflow_stages: list[dict[str, Any]] = Field(default_factory=list)
    workflow_labels: list[dict[str, Any]] = Field(default_factory=list)
    workflow_tags: list[dict[str, Any]] = Field(default_factory=list)
    status_definitions: list[dict[str, Any]] = Field(default_factory=list)
    workflow_runs: list[dict[str, Any]] = Field(default_factory=list)
    workflow_run_steps: list[dict[str, Any]] = Field(default_factory=list)
    preferences: list[dict[str, Any]] = Field(default_factory=list)
    versions: list[dict[str, Any]] = Field(default_factory=list)

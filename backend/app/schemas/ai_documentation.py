from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class DocumentationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=12000)
    complaints: list[str] = Field(default_factory=list, max_length=30)
    vitals: list[str] = Field(default_factory=list, max_length=30)
    diagnoses: list[str] = Field(default_factory=list, max_length=30)
    treatments: list[str] = Field(default_factory=list, max_length=30)
    prescriptions: list[str] = Field(default_factory=list, max_length=50)
    advice: str = Field(default="", max_length=3000)
    followup: str = Field(default="", max_length=500)


class DocumentationSections(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subjective: str = Field(max_length=6000)
    objective: str = Field(max_length=4000)
    assessment: str = Field(max_length=4000)
    plan: str = Field(max_length=6000)


class DocumentationDraft(DocumentationSections):
    mode: Literal["ai", "template"]
    missing_sections: list[str]
    source_digest: str

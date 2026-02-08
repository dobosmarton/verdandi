"""Models for Step 3: MVP Definition."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


class Feature(BaseModel):
    """A feature to highlight on the landing page."""

    model_config = ConfigDict(frozen=True)

    title: str
    description: str
    icon_name: str = Field(default="", description="Optional icon identifier for the template")


class MVPDefinition(BaseStepResult):
    """Output of Step 3: what to build and how to present it."""

    step_name: str = "mvp_definition"

    product_name: str
    tagline: str = Field(description="Short, memorable tagline")
    value_proposition: str
    target_persona: str = Field(description="Specific person description, not a segment")

    features: list[Feature] = Field(min_length=1, max_length=6)
    pricing_model: str = Field(description="Free/freemium/paid + price point")
    cta_text: str = Field(default="Get Early Access", description="Call-to-action button text")
    cta_subtext: str = Field(
        default="", description="Text below CTA, e.g. 'No credit card required'"
    )

    domain_suggestions: list[str] = Field(
        default_factory=list,
        description="Suggested domain names to check availability",
    )
    color_scheme: str = Field(default="blue", description="Primary color for landing page")

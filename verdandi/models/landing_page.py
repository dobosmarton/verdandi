"""Models for Step 4: Landing Page Generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


class Testimonial(BaseModel):
    """A (fabricated for validation) testimonial."""

    model_config = ConfigDict(frozen=True)

    quote: str
    author_name: str
    author_title: str


class FAQItem(BaseModel):
    """A frequently asked question."""

    model_config = ConfigDict(frozen=True)

    question: str
    answer: str


class LandingPageContent(BaseStepResult):
    """Output of Step 4: all content needed to render a landing page."""

    step_name: str = "landing_page"

    # Hero section
    headline: str
    subheadline: str
    hero_cta_text: str = "Get Early Access"
    hero_cta_subtext: str = ""

    # Features section
    features_title: str = "Features"
    features: list[dict] = Field(
        default_factory=list,
        description="List of {title, description, icon} dicts",
    )

    # Social proof
    testimonials: list[Testimonial] = Field(default_factory=list)
    stats: list[dict] = Field(
        default_factory=list,
        description="List of {value, label} dicts, e.g. {'value': '10x', 'label': 'faster'}",
    )

    # FAQ
    faq_items: list[FAQItem] = Field(default_factory=list)

    # Footer CTA
    footer_cta_headline: str = ""
    footer_cta_text: str = ""

    # Meta
    page_title: str = ""
    meta_description: str = ""
    og_title: str = ""
    og_description: str = ""

    # Rendered output
    rendered_html: str = Field(default="", description="Final HTML after template fill")
    template_used: str = "landing_v1.html"

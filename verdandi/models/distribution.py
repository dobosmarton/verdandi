"""Models for Step 9: Distribution."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


class SocialPost(BaseModel):
    """A post published to a social platform."""

    model_config = ConfigDict(frozen=True)

    platform: str = Field(description="linkedin/twitter/reddit/bluesky")
    content: str
    url: str = Field(default="", description="URL of the published post")
    posted: bool = False
    engagement: dict = Field(
        default_factory=dict,
        description="Likes, comments, shares if available",
    )


class SEOSubmission(BaseModel):
    """SEO metadata submission."""

    model_config = ConfigDict(frozen=True)

    google_search_console_submitted: bool = False
    sitemap_url: str = ""
    indexed: bool = False


class DistributionResult(BaseStepResult):
    """Output of Step 9: distribution actions taken."""

    step_name: str = "distribution"

    social_posts: list[SocialPost] = Field(default_factory=list)
    seo: SEOSubmission = Field(default_factory=SEOSubmission)
    total_reach_estimate: int = 0

"""Models for Steps 6-8: Domain Purchase, Deploy, Analytics Setup."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


class DomainInfo(BaseModel):
    """Domain registration details."""

    model_config = ConfigDict(frozen=True)

    domain: str = ""
    registrar: str = "porkbun"
    purchased: bool = False
    cost_usd: float = 0.0
    nameservers: list[str] = Field(default_factory=list)


class CloudflareDeployment(BaseModel):
    """Cloudflare Pages deployment details."""

    model_config = ConfigDict(frozen=True)

    project_name: str = ""
    deployment_url: str = ""
    custom_domain: str = ""
    ssl_active: bool = False
    deployment_id: str = ""


class AnalyticsSetup(BaseModel):
    """Umami analytics configuration."""

    model_config = ConfigDict(frozen=True)

    website_id: str = ""
    tracking_script_url: str = ""
    dashboard_url: str = ""
    injected: bool = False


class DeploymentResult(BaseStepResult):
    """Combined output of Steps 6-8."""

    step_name: str = "deployment"

    domain: DomainInfo = Field(default_factory=DomainInfo)
    cloudflare: CloudflareDeployment = Field(default_factory=CloudflareDeployment)
    analytics: AnalyticsSetup = Field(default_factory=AnalyticsSetup)
    live_url: str = ""

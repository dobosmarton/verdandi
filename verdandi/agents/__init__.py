"""Import all agent steps to trigger registration."""

from verdandi.agents.analytics import AnalyticsSetupStep
from verdandi.agents.base import PriorResults
from verdandi.agents.deploy import DeployStep
from verdandi.agents.discovery import IdeaDiscoveryStep
from verdandi.agents.distribution import DistributionStep
from verdandi.agents.domain import DomainPurchaseStep
from verdandi.agents.human_review import HumanReviewStep
from verdandi.agents.landing_page import LandingPageStep
from verdandi.agents.monitor import MonitorStep
from verdandi.agents.mvp import MVPDefinitionStep
from verdandi.agents.research import DeepResearchStep
from verdandi.agents.scoring import ScoringStep

__all__ = [
    "AnalyticsSetupStep",
    "DeepResearchStep",
    "DeployStep",
    "DistributionStep",
    "DomainPurchaseStep",
    "HumanReviewStep",
    "IdeaDiscoveryStep",
    "LandingPageStep",
    "MVPDefinitionStep",
    "MonitorStep",
    "PriorResults",
    "ScoringStep",
]

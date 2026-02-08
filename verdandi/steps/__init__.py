"""Import all steps to trigger registration."""

from verdandi.steps.s0_idea_discovery import IdeaDiscoveryStep  # noqa: F401
from verdandi.steps.s1_deep_research import DeepResearchStep  # noqa: F401
from verdandi.steps.s2_scoring import ScoringStep  # noqa: F401
from verdandi.steps.s3_mvp_definition import MVPDefinitionStep  # noqa: F401
from verdandi.steps.s4_landing_page import LandingPageStep  # noqa: F401
from verdandi.steps.s5_human_review import HumanReviewStep  # noqa: F401
from verdandi.steps.s6_domain_purchase import DomainPurchaseStep  # noqa: F401
from verdandi.steps.s7_deploy import DeployStep  # noqa: F401
from verdandi.steps.s8_analytics_setup import AnalyticsSetupStep  # noqa: F401
from verdandi.steps.s9_distribution import DistributionStep  # noqa: F401
from verdandi.steps.s10_monitor import MonitorStep  # noqa: F401

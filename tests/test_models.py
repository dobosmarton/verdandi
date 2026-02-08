"""Tests for Pydantic domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from verdandi.models.deployment import (
    DeploymentResult,
    DomainInfo,
)
from verdandi.models.distribution import DistributionResult, SocialPost
from verdandi.models.experiment import Experiment, ExperimentStatus
from verdandi.models.idea import IdeaCandidate, PainPoint
from verdandi.models.landing_page import FAQItem, LandingPageContent, Testimonial
from verdandi.models.scoring import Decision, PreBuildScore, ScoreComponent
from verdandi.models.validation import MetricsSnapshot, ValidationDecision, ValidationReport


class TestExperiment:
    def test_create_minimal(self):
        exp = Experiment()
        assert exp.id is None
        assert exp.status == ExperimentStatus.PENDING
        assert exp.current_step == 0

    def test_create_with_fields(self):
        exp = Experiment(
            idea_title="Test Product",
            idea_summary="A cool product",
            status=ExperimentStatus.RUNNING,
        )
        assert exp.idea_title == "Test Product"
        assert exp.status == ExperimentStatus.RUNNING

    def test_frozen(self):
        exp = Experiment(idea_title="Test")
        with pytest.raises(ValidationError):
            exp.idea_title = "Changed"

    def test_model_copy_update(self):
        exp = Experiment(idea_title="Original")
        updated = exp.model_copy(update={"idea_title": "Updated"})
        assert updated.idea_title == "Updated"
        assert exp.idea_title == "Original"

    def test_serialization_roundtrip(self):
        exp = Experiment(
            idea_title="Roundtrip Test",
            status=ExperimentStatus.COMPLETED,
            current_step=10,
        )
        json_str = exp.model_dump_json()
        restored = Experiment.model_validate_json(json_str)
        assert restored.idea_title == exp.idea_title
        assert restored.status == exp.status
        assert restored.current_step == exp.current_step


class TestIdeaCandidate:
    def test_create(self):
        idea = IdeaCandidate(
            experiment_id=1,
            title="DevLog",
            one_liner="Automated changelogs",
            problem_statement="Developers hate writing changelogs",
            target_audience="Software developers",
            category="developer-tools",
            pain_points=[
                PainPoint(
                    description="Manual changelog writing",
                    severity=8,
                    frequency="daily",
                    source="HN",
                ),
            ],
        )
        assert idea.title == "DevLog"
        assert len(idea.pain_points) == 1

    def test_frozen(self):
        idea = IdeaCandidate(
            experiment_id=1,
            title="Test",
            one_liner="Test",
            problem_statement="Test",
            target_audience="Test",
            category="test",
        )
        with pytest.raises(ValidationError):
            idea.title = "Changed"


class TestScoring:
    def test_decision_enum(self):
        assert Decision.GO == "go"
        assert Decision.NO_GO == "no_go"
        assert Decision.ITERATE == "iterate"

    def test_score_component(self):
        comp = ScoreComponent(name="pain_severity", score=85, weight=0.25, reasoning="High")
        assert comp.score == 85

    def test_prebuild_score(self):
        score = PreBuildScore(
            experiment_id=1,
            total_score=75,
            decision=Decision.GO,
            components=[
                ScoreComponent(name="pain", score=80, weight=0.5, reasoning="High pain"),
                ScoreComponent(name="market", score=70, weight=0.5, reasoning="Large market"),
            ],
        )
        assert score.decision == Decision.GO
        assert len(score.components) == 2


class TestLandingPage:
    def test_faq_item(self):
        faq = FAQItem(question="How?", answer="Like this.")
        assert faq.question == "How?"

    def test_testimonial_creation(self):
        t = Testimonial(quote="Great!", author_name="Alice", author_title="CEO")
        assert t.author_name == "Alice"

    def test_landing_page_content(self):
        content = LandingPageContent(
            experiment_id=1,
            headline="Test Headline",
            subheadline="Test Subheadline",
            hero_cta_text="Sign Up",
        )
        assert content.headline == "Test Headline"
        assert content.rendered_html == ""


class TestDeployment:
    def test_domain_info_defaults(self):
        d = DomainInfo()
        assert d.domain == ""
        assert d.registrar == "porkbun"
        assert d.purchased is False

    def test_deployment_result_defaults(self):
        dr = DeploymentResult(experiment_id=1)
        assert dr.domain.domain == ""
        assert dr.cloudflare.project_name == ""
        assert dr.analytics.website_id == ""

    def test_deployment_result_with_domain(self):
        dr = DeploymentResult(
            experiment_id=1,
            domain=DomainInfo(domain="test.xyz", purchased=True, cost_usd=2.0),
            live_url="https://test.xyz",
        )
        assert dr.domain.purchased is True
        assert dr.live_url == "https://test.xyz"


class TestDistribution:
    def test_social_post(self):
        post = SocialPost(platform="twitter", content="Hello!", posted=True)
        assert post.platform == "twitter"

    def test_distribution_result(self):
        dr = DistributionResult(
            experiment_id=1,
            social_posts=[SocialPost(platform="twitter", content="Hello!", posted=True)],
        )
        assert len(dr.social_posts) == 1


class TestValidation:
    def test_metrics_snapshot(self):
        m = MetricsSnapshot(
            total_visitors=500,
            unique_visitors=400,
            bounce_rate=55.0,
            avg_time_on_page=45.0,
            cta_clicks=75,
            email_signups=50,
        )
        assert m.total_visitors == 500

    def test_validation_report(self):
        report = ValidationReport(
            experiment_id=1,
            decision=ValidationDecision.GO,
            metrics=MetricsSnapshot(
                total_visitors=500,
                unique_visitors=400,
                bounce_rate=55.0,
                avg_time_on_page=45.0,
                cta_clicks=75,
                email_signups=50,
            ),
            email_signup_rate=10.0,
            cta_click_rate=15.0,
        )
        assert report.decision == ValidationDecision.GO

"""Step 4: Landing Page Generation — generate content and render HTML."""

from __future__ import annotations

from importlib.resources import files

import structlog
from pydantic import BaseModel, ConfigDict

from verdandi.models.landing_page import (
    FAQItem,
    FeatureItem,
    LandingPageContent,
    StatItem,
    Testimonial,
)
from verdandi.steps.base import AbstractStep, StepContext, register_step

logger = structlog.get_logger()


class _LandingPageLLMOutput(BaseModel):
    """LLM-generated landing page content fields (no metadata)."""

    model_config = ConfigDict(frozen=True)

    headline: str
    subheadline: str
    hero_cta_text: str
    hero_cta_subtext: str
    features_title: str
    features: list[FeatureItem]
    testimonials: list[Testimonial]
    stats: list[StatItem]
    faq_items: list[FAQItem]
    footer_cta_headline: str
    footer_cta_text: str
    page_title: str
    meta_description: str
    og_title: str
    og_description: str


@register_step
class LandingPageStep(AbstractStep):
    name = "landing_page"
    step_number = 4

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            content = self._mock_content(ctx)
            rendered = self._render_template(content)
            return content.model_copy(update={"rendered_html": rendered})

        from verdandi.llm import LLMClient
        from verdandi.models.mvp import MVPDefinition

        experiment_id = ctx.experiment.id
        if experiment_id is None:
            raise RuntimeError("Experiment has no ID — cannot generate landing page")

        # Retrieve Step 3 result
        mvp_result = ctx.db.get_step_result(experiment_id, "mvp_definition")
        if mvp_result is None:
            msg = (
                f"Cannot generate landing page: Step 3 (mvp_definition) "
                f"not found for experiment {ctx.experiment.id}"
            )
            raise RuntimeError(msg)

        mvp_data = mvp_result["data"]
        if not isinstance(mvp_data, dict):
            msg = f"Invalid MVP definition data for experiment {ctx.experiment.id}"
            raise RuntimeError(msg)

        mvp = MVPDefinition.model_validate(mvp_data)

        # Build the features list for the prompt
        features_text = "\n".join(f"- {f.title}: {f.description}" for f in mvp.features)

        system_prompt = (
            "You are a conversion copywriter creating landing page content "
            "for a product validation test. Write specific, concrete copy — "
            "no generic phrases. The testimonials should be realistic "
            "(fabricated for validation purposes). Create 3-4 features, "
            "2-3 testimonials, 3 stats, and 3-4 FAQ items. The copy should "
            "directly address the target audience's pain points."
        )

        user_prompt = (
            f"Create landing page content for the following product:\n\n"
            f"Product Name: {mvp.product_name}\n"
            f"Tagline: {mvp.tagline}\n"
            f"Value Proposition: {mvp.value_proposition}\n"
            f"Target Persona: {mvp.target_persona}\n"
            f"Features:\n{features_text}\n"
            f"Pricing Model: {mvp.pricing_model}\n"
            f"CTA Text: {mvp.cta_text}\n\n"
            f"Generate compelling, specific landing page copy that speaks "
            f"directly to the target persona's pain points. Avoid generic "
            f"marketing language. Each feature icon should be a single "
            f"lowercase word (e.g. 'zap', 'shield', 'clock', 'chart')."
        )

        logger.info(
            "Generating landing page content via LLM",
            experiment_id=ctx.experiment.id,
            product_name=mvp.product_name,
        )

        llm = LLMClient(ctx.settings)
        result = llm.generate(
            user_prompt,
            _LandingPageLLMOutput,
            system=system_prompt,
        )

        content = LandingPageContent(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            headline=result.headline,
            subheadline=result.subheadline,
            hero_cta_text=result.hero_cta_text,
            hero_cta_subtext=result.hero_cta_subtext,
            features_title=result.features_title,
            features=result.features,
            testimonials=result.testimonials,
            stats=result.stats,
            faq_items=result.faq_items,
            footer_cta_headline=result.footer_cta_headline,
            footer_cta_text=result.footer_cta_text,
            page_title=result.page_title,
            meta_description=result.meta_description,
            og_title=result.og_title,
            og_description=result.og_description,
        )

        rendered = self._render_template(content)

        logger.info(
            "Landing page content generated",
            experiment_id=ctx.experiment.id,
            headline=content.headline,
            num_features=len(content.features),
            num_testimonials=len(content.testimonials),
            rendered_length=len(rendered),
        )

        return content.model_copy(update={"rendered_html": rendered})

    def _render_template(self, content: LandingPageContent) -> str:
        """Fill the landing page template with content."""
        try:
            template_html = (
                files("verdandi").joinpath("templates", content.template_used).read_text()
            )
        except (FileNotFoundError, TypeError):
            return "<html><body><h1>Template not found</h1></body></html>"

        replacements = {
            "{{HEADLINE}}": content.headline,
            "{{SUBHEADLINE}}": content.subheadline,
            "{{CTA_TEXT}}": content.hero_cta_text,
            "{{CTA_SUBTEXT}}": content.hero_cta_subtext,
            "{{FEATURES_TITLE}}": content.features_title,
            "{{PAGE_TITLE}}": content.page_title,
            "{{META_DESCRIPTION}}": content.meta_description,
            "{{OG_TITLE}}": content.og_title,
            "{{OG_DESCRIPTION}}": content.og_description,
            "{{FOOTER_CTA_HEADLINE}}": content.footer_cta_headline,
            "{{FOOTER_CTA_TEXT}}": content.footer_cta_text,
        }

        # Build features HTML
        features_html = ""
        for feat in content.features:
            features_html += f"""
            <div class="p-6 bg-white rounded-lg shadow-sm border">
                <h3 class="text-lg font-semibold mb-2">{feat.get("title", "")}</h3>
                <p class="text-gray-600">{feat.get("description", "")}</p>
            </div>"""
        replacements["{{FEATURES_HTML}}"] = features_html

        # Build stats HTML
        stats_html = ""
        for stat in content.stats:
            stats_html += f"""
            <div>
                <p class="text-3xl font-bold text-indigo-600">{stat.get("value", "")}</p>
                <p class="text-sm text-gray-500 mt-1">{stat.get("label", "")}</p>
            </div>"""
        replacements["{{STATS_HTML}}"] = stats_html

        # Analytics script placeholder (empty unless injected later)
        replacements["{{ANALYTICS_SCRIPT}}"] = ""

        # Build FAQ HTML
        faq_html = ""
        for faq in content.faq_items:
            faq_html += f"""
            <div class="border-b py-4">
                <h3 class="font-semibold text-lg mb-2">{faq.question}</h3>
                <p class="text-gray-600">{faq.answer}</p>
            </div>"""
        replacements["{{FAQ_HTML}}"] = faq_html

        # Build testimonials HTML
        testimonials_html = ""
        for t in content.testimonials:
            testimonials_html += f"""
            <div class="p-6 bg-gray-50 rounded-lg">
                <p class="text-gray-700 italic mb-4">"{t.quote}"</p>
                <p class="font-semibold">{t.author_name}</p>
                <p class="text-sm text-gray-500">{t.author_title}</p>
            </div>"""
        replacements["{{TESTIMONIALS_HTML}}"] = testimonials_html

        html = template_html
        for token, value in replacements.items():
            html = html.replace(token, value)
        return html

    def _mock_content(self, ctx: StepContext) -> LandingPageContent:
        title = ctx.experiment.idea_title
        return LandingPageContent(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            headline=f"{title}: Automate What You Hate",
            subheadline="Stop wasting hours on repetitive tasks. Get AI-powered automation that works out of the box.",
            hero_cta_text="Get Early Access",
            hero_cta_subtext="Free during beta. No credit card required.",
            features_title="Everything You Need",
            features=[
                {
                    "title": "One-Click Setup",
                    "description": "Connect your tools and start in 60 seconds",
                    "icon": "zap",
                },
                {
                    "title": "AI-Powered",
                    "description": "Smart automation that adapts to your workflow",
                    "icon": "brain",
                },
                {
                    "title": "Real-Time Alerts",
                    "description": "Know immediately when something needs attention",
                    "icon": "bell",
                },
            ],
            testimonials=[
                Testimonial(
                    quote="This saved me 5 hours every week",
                    author_name="Alex Chen",
                    author_title="Founder, TechStartup",
                ),
                Testimonial(
                    quote="The setup took literally 30 seconds",
                    author_name="Jordan Lee",
                    author_title="CTO, SmallSaaS",
                ),
            ],
            stats=[
                {"value": "10x", "label": "faster than manual"},
                {"value": "60s", "label": "setup time"},
                {"value": "500+", "label": "beta users"},
            ],
            faq_items=[
                FAQItem(
                    question="How does it work?",
                    answer="Connect your existing tools via our simple integration. Our AI analyzes your workflow and automates the repetitive parts.",
                ),
                FAQItem(
                    question="Is it free?",
                    answer="Yes, during the beta period. We plan to offer a generous free tier and a pro plan at $19/month.",
                ),
                FAQItem(
                    question="What integrations do you support?",
                    answer="We integrate with all major tools in this space. More integrations are added weekly.",
                ),
            ],
            footer_cta_headline="Ready to save time?",
            footer_cta_text="Get Early Access",
            page_title=f"{title} — Automate What You Hate",
            meta_description=f"{title} helps you automate repetitive tasks with AI. Free during beta.",
            og_title=f"{title} — Automate What You Hate",
            og_description="AI-powered automation for busy founders and developers.",
        )

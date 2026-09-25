"""Planner implementation (Workstream D)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from deckforge_core.config import Settings
from deckforge_core.errors import DeckForgeError, LLMError
from deckforge_core.planner.lint import autofix_issues, lint_deck_plan
from deckforge_core.planner.prompts import plan_system_message, plan_user_message
from deckforge_core.providers.llm import LLMProvider, Message
from deckforge_core.schemas.deck_plan import (
    ChartSeries,
    ChartSpec,
    DeckPlan,
    DiagramSpec,
    GraphEdge,
    GraphNode,
    GraphSpec,
    ImageReq,
    SlidePlan,
    SlotValue,
)
from deckforge_core.schemas.pack import FormatPack

last_warnings: list[str] = []


@dataclass
class PlannerOptions:
    slide_count: int = 10
    tone: str = "professional"
    audience: str = ""
    aspect_ratio: str = "16:9"
    image_queries: bool = False


class TemplatePlanner:
    """Deterministic, zero-network planner."""

    def plan(
        self,
        prompt: str,
        pack: FormatPack,
        options: Optional[PlannerOptions] = None,
    ) -> DeckPlan:
        if options is None:
            options = PlannerOptions()

        topic = self._extract_topic(prompt)
        slides: list[SlidePlan] = []

        # 1. title slide
        slides.append(
            SlidePlan(
                n=1,
                archetype="title",
                title=topic,
                slots={
                    "kicker": SlotValue(text=" "),
                    "title": SlotValue(text=topic),
                    "subtitle": SlotValue(
                        text=f"{options.tone} update" if options.tone else "Update"
                    ),
                },
            )
        )

        # 2. agenda slide
        agenda_items = self._derive_agenda_items(prompt)
        slides.append(
            SlidePlan(
                n=2,
                archetype="agenda",
                title="Agenda",
                slots={"items": SlotValue(items=agenda_items)},
            )
        )

        # 3. content slides
        archetype_order = list(pack.default_archetype_order or [])
        if not archetype_order:
            archetype_order = [
                "big-number",
                "two-column-text",
                "three-cards",
                "comparison",
                "timeline",
                "process-flow",
                "chart",
                "statement",
                "image-left",
                "image-right",
            ]
        # drop structural archetypes from the rotation
        structural = {"title", "agenda", "closing", "section-divider"}
        content_order = [a for a in archetype_order if a not in structural]
        if not content_order:
            content_order = ["big-number", "two-column-text", "three-cards"]

        content_count = max(0, options.slide_count - 3)
        for i in range(content_count):
            slide_n = 3 + i
            arch = content_order[i % len(content_order)]
            slides.append(self._build_content_slide(slide_n, arch, topic, options))

        # closing slide
        slides.append(
            SlidePlan(
                n=len(slides) + 1,
                archetype="closing",
                title="Next steps",
                slots={
                    "kicker": SlotValue(text=" "),
                    "title": SlotValue(text="Next steps"),
                    "contact": SlotValue(paragraphs=["Contact for follow-up"]),
                },
            )
        )

        final_slides = [
            s.model_copy(update={"n": idx}) for idx, s in enumerate(slides, start=1)
        ]

        plan = DeckPlan(
            title=topic,
            aspect_ratio=options.aspect_ratio,
            created_by="template-planner",
            pack=pack.name if pack else "demo",
            slides=final_slides,
        )

        plan = DeckPlan.model_validate(plan.model_dump(mode="json"))

        issues = lint_deck_plan(plan)
        banned = [i for i in issues if i.check == "banned-phrase"]
        assert not banned, "template planner emitted banned phrases"
        plan, _ = autofix_issues(plan)
        return plan

    def _extract_topic(self, prompt: str) -> str:
        if not prompt:
            return "Topic"
        text = prompt.strip()
        for sep in (".", "!", "?", "\n"):
            if sep in text:
                text = text.split(sep)[0]
                break
        return text.strip().strip('"').strip("'") or "Topic"

    def _derive_agenda_items(self, prompt: str) -> list[str]:
        p = prompt.lower()
        if "context" in p or "background" in p:
            first = "Context"
        else:
            first = "Context"
        if "evidence" in p or "data" in p or "result" in p:
            second = "Evidence"
        else:
            second = "Key findings"
        if "recommend" in p or "next" in p or "action" in p:
            third = "Recommendation"
        else:
            third = "Recommendation"
        items = [first, second, third]
        while len(items) < 3:
            items.append("Next steps")
        return items[:5]

    def _build_content_slide(
        self, slide_n: int, arch: str, topic: str, options: PlannerOptions
    ) -> SlidePlan:
        if arch == "big-number":
            return SlidePlan(
                n=slide_n,
                archetype="big-number",
                title=f"{topic} metric",
                slots={
                    "number": SlotValue(text="12%"),
                    "caption": SlotValue(text="example; verify"),
                },
            )
        elif arch == "three-cards":
            return SlidePlan(
                n=slide_n,
                archetype="three-cards",
                title=topic,
                slots={
                    "card_1": SlotValue(
                        text=f"{topic} strength",
                        paragraphs=["Clear benefit based on context"],
                    ),
                    "card_2": SlotValue(
                        text=f"{topic} challenge",
                        paragraphs=["Practical consideration to address"],
                    ),
                    "card_3": SlotValue(
                        text=f"{topic} opportunity",
                        paragraphs=["Specific action to capture value"],
                    ),
                },
            )
        elif arch == "two-column-text":
            return SlidePlan(
                n=slide_n,
                archetype="two-column-text",
                title=topic,
                slots={
                    "col_a_heading": SlotValue(text="Current state"),
                    "col_a_body": SlotValue(
                        paragraphs=[f"Specific details about {topic.lower()}"]
                    ),
                    "col_b_heading": SlotValue(text="Proposed approach"),
                    "col_b_body": SlotValue(paragraphs=["Concrete steps to move forward"]),
                },
            )
        elif arch == "chart":
            return SlidePlan(
                n=slide_n,
                archetype="chart",
                title=f"{topic} trend",
                slots={
                    "chart": SlotValue(
                        chart=ChartSpec(
                            chart_type="column",
                            categories=["Q1", "Q2", "Q3", "Q4"],
                            series=[
                                ChartSeries(
                                    name="Value",
                                    values=[10.0, 20.0, 30.0, 40.0],
                                    color_role="accent1",
                                )
                            ],
                            units="units",
                            show_legend=True,
                        )
                    ),
                    "source": SlotValue(text="example data"),
                },
            )
        elif arch == "process-flow":
            graph = GraphSpec(
                directed=True,
                nodes=[
                    GraphNode(id="n1", label="Start"),
                    GraphNode(id="n2", label=f"{topic} step"),
                    GraphNode(id="n3", label="Outcome"),
                ],
                edges=[
                    GraphEdge(src="n1", dst="n2"),
                    GraphEdge(src="n2", dst="n3"),
                ],
            )
            return SlidePlan(
                n=slide_n,
                archetype="process-flow",
                title=f"{topic} process",
                slots={
                    "diagram": SlotValue(diagram=DiagramSpec(graph=graph)),
                    "caption": SlotValue(text="Process overview"),
                },
            )
        elif arch in ("image-left", "image-right"):
            slot = {"title": SlotValue(text=topic)}
            if options.image_queries:
                slot["image"] = SlotValue(image=ImageReq(query=f"photo of {topic}"))
            else:
                slot["image"] = SlotValue(text="")
            slot["body"] = SlotValue(
                paragraphs=[f"Specific explanation of {topic.lower()}"]
            )
            return SlidePlan(
                n=slide_n,
                archetype=arch,
                title=topic,
                slots=slot,
            )
        elif arch == "timeline":
            return SlidePlan(
                n=slide_n,
                archetype="timeline",
                title=f"{topic} timeline",
                slots={
                    "items": SlotValue(
                        items=[
                            "2024|First step|Initial action taken",
                            "2025|Key milestone|Progress achieved",
                            "2026|Target goal|Planned outcome",
                        ]
                    )
                },
            )
        else:
            return SlidePlan(
                n=slide_n,
                archetype=arch,
                title=f"{topic} point",
                slots={"statement": SlotValue(text=f"{topic} point")},
            )


class LLMPLanner:
    """Wraps a provider to generate deck plans."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def plan(
        self,
        prompt: str,
        pack: FormatPack,
        options: Optional[PlannerOptions] = None,
    ) -> DeckPlan:
        if options is None:
            options = PlannerOptions()

        messages = [
            Message(
                role="system",
                content=plan_system_message(pack, options.__dict__),
            ),
            Message(
                role="user",
                content=plan_user_message(prompt, options.__dict__),
            ),
        ]

        try:
            plan = self.provider.complete_structured(
                messages,
                output_model=DeckPlan,
                model=None,
                temperature=0.4,
                max_tokens=8192,
            )
        except (LLMError, DeckForgeError) as exc:
            last_warnings.clear()
            last_warnings.append(f"LLM planning failed; falling back to template: {exc}")
            return TemplatePlanner().plan(prompt, pack, options)

        try:
            plan_fixed, _ = autofix_issues(plan)
            plan = plan_fixed
        except Exception:
            pass
        return plan


def plan_deck(
    prompt: str,
    pack: FormatPack,
    *,
    options: Optional[PlannerOptions] = None,
    settings: Optional[Settings] = None,
    llm_provider: Optional[str] = None,
) -> DeckPlan:
    if settings is None:
        settings = Settings()

    provider_name = llm_provider or settings.get("llm_provider") or "mock"

    use_llm = False
    if llm_provider is not None:
        # explicit provider override is honored even in local-only mode
        use_llm = True
    elif settings.local_only:
        use_llm = False
    elif provider_name == "mock":
        use_llm = False
    else:
        use_llm = True

    if not use_llm:
        return TemplatePlanner().plan(prompt, pack, options)

    try:
        from deckforge_core.providers.registry_bootstrap import default_llm

        provider = default_llm(settings)
        return LLMPLanner(provider).plan(prompt, pack, options)
    except Exception as exc:
        last_warnings.clear()
        last_warnings.append(f"Provider init failed; falling back to template: {exc}")
        return TemplatePlanner().plan(prompt, pack, options)

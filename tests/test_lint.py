
from deckforge_core.planner.lint import (
    BANNED_PHRASES,
    autofix_issues,
    lint_deck_plan,
    lint_text,
)
from deckforge_core.schemas.deck_plan import DeckPlan, SlidePlan


def test_banned_phrases_flagged():
    for phrase in BANNED_PHRASES[:5]:
        issues = lint_text(f"This contains {phrase} in text")
        assert any(i.check == "banned-phrase" for i in issues)


def test_clean_text_passes():
    issues = lint_text("This is clean professional text.")
    assert len(issues) == 0


def test_em_dash_overuse_flagged():
    text = "Word — dash — another — third"
    issues = lint_text(text)
    assert any(i.check == "em-dash-overuse" for i in issues)


def test_emoji_bullet_flagged():
    issues = lint_text("- 😀 emoji bullet")
    assert any(i.check == "emoji-bullet" for i in issues)


def test_topic_style_title_flagged_but_not_takeaway():
    # Create a simple deck
    plan = DeckPlan(
        title="Test",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="title",
                title="Overview",
                slots={},
            )
        ],
    )
    issues = lint_deck_plan(plan)
    assert any(i.check == "topic-style-title" for i in issues)

    # Takeaway style should not be flagged as topic-style title
    plan2 = DeckPlan(
        title="Test",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="title",
                title="Churn fell 12% after onboarding changes",
                slots={},
            )
        ],
    )
    issues2 = lint_deck_plan(plan2)
    assert not any(i.check == "topic-style-title" for i in issues2)


def test_autofix_issues_removes_leverage():
    plan = DeckPlan(
        title="Test",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="title",
                title="We need to leverage our data",
                slots={},
            )
        ],
    )
    fixed, changed = autofix_issues(plan)
    assert changed
    assert "use" in fixed.slides[0].title.lower()
    assert "leverage" not in fixed.slides[0].title.lower()


def test_repeated_opener_flagged():
    text = "\n".join(
        [
            "We found the result improved",
            "We found the error rate fell",
            "We found the users returned",
        ]
    )
    issues = lint_text(text)
    assert any(i.check == "repeated-opener" for i in issues)

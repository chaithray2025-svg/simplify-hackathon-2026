"""
Agent 4 — Reply Drafting Agent.

What it does: review text + sentiment -> a drafted customer-facing reply.
Single Bedrock call, no loop, no tools. Deliberately the lightest agent
(per PROJECT_PLAN.md) — cheap model, simple prompt.

Model: Claude Haiku 4.5, temperature left at default (some natural variation
is fine here, unlike the Extraction Agent which wants temperature=0).
"""

from bedrock_client import ask_claude

SYSTEM_PROMPT = """You are drafting a business's public reply to a single customer review.

Rules:
- Reply in the SAME language as the review (see the `language` field passed to you).
- Keep it short: 2-4 sentences.
- If sentiment is negative: acknowledge the specific issue, apologize briefly, state one concrete thing being done about it. Do not sound defensive or make excuses.
- If sentiment is positive: thank them specifically for what they praised, don't be generic ("Thanks for your feedback!" is not acceptable — reference what they actually said).
- If sentiment is neutral/mixed: acknowledge both the positive and the concern briefly.
- Never invent specifics (names, dates, compensation, policies) that weren't in the review or given to you.
- Output ONLY the reply text — no preamble, no quotation marks, no "Here's a draft:"."""


def draft_reply(review_text: str, sentiment: str, language: str = "en") -> str:
    """
    Draft a customer-facing reply to one review.

    Args:
        review_text: the original review text (any language).
        sentiment: "positive" | "negative" | "neutral" (or "mixed").
        language: ISO 639-1 code of the review's language (e.g. "en", "zh", "ms", "ta").
            The reply is drafted in this same language.

    Returns:
        The drafted reply text.
    """
    prompt = (
        f"Review (language={language}, sentiment={sentiment}):\n"
        f'"{review_text}"\n\n'
        f"Draft the reply now, in {language}."
    )
    return ask_claude(prompt, system=SYSTEM_PROMPT, max_tokens=300)


if __name__ == "__main__":
    examples = [
        {
            "review_text": "Waited 15 minutes just to order at lunch, and the food came out cold.",
            "sentiment": "negative",
            "language": "en",
        },
        {
            "review_text": "The laksa was amazing, best I've had in years!",
            "sentiment": "positive",
            "language": "en",
        },
    ]
    for ex in examples:
        reply = draft_reply(**ex)
        print(f"Review: {ex['review_text']}")
        print(f"Reply:  {reply}")
        print()

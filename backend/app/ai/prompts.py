"""Prompts and the response schema for ticket analysis."""

from app.models import TicketPriority

ANALYSIS_SYSTEM = (
    "You triage support tickets for a company IT help desk. "
    "Reply only with JSON matching the schema. Be concise and factual; "
    "never invent details that aren't in the ticket."
)

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": "Two or three words, e.g. 'network', 'billing', 'account access'",
        },
        "priority": {"type": "string", "enum": [p.value for p in TicketPriority]},
        "required_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-5 short lowercase skill tags, e.g. 'vpn', 'networking'",
        },
        "summary": {"type": "string", "description": "One sentence restating the problem"},
    },
    "required": ["category", "priority", "required_skills", "summary"],
}

NOTES_SYSTEM = (
    "You help a support moderator solve a ticket fast. "
    "Write short, practical notes in Markdown: likely cause, what to check first, "
    "and questions to ask the user if information is missing. "
    "No greetings, no sign-off, at most 200 words. "
    "Say plainly when the ticket lacks the detail needed to diagnose it."
)


def analysis_prompt(title: str, description: str) -> str:
    return f"Classify this support ticket.\n\nTitle: {title}\n\nDescription:\n{description}"


def notes_prompt(title: str, description: str, category: str, priority: str) -> str:
    return (
        f"Write helpful notes for the moderator who will solve this ticket.\n\n"
        f"Title: {title}\nCategory: {category}\nPriority: {priority}\n\n"
        f"Description:\n{description}"
    )

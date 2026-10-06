"""Summary agent: the case brief a claims handler reads first, plus a draft reply.

No tools: the pipeline hands it everything already gathered. The recommendation is advisory;
the handler decides, and the CRM shows the deterministic coverage result next to it.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from aip.agents.runtime import AgentSpec

VERSION = "1.0"


class Recommendation(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_INFORMATION = "request_information"
    REFER_SENIOR = "refer_senior"


class HandlerSummary(BaseModel):
    summary_sk: str = Field(description="Case summary in Slovak, 4-8 sentences")
    key_facts: list[str] = Field(description="Short Slovak bullet points with the key facts")
    open_questions: list[str] = Field(description="What is unclear or contradictory")
    recommendation: Recommendation
    recommendation_rationale: str = Field(description="In Slovak, citing the coverage reasons")
    draft_customer_message: str = Field(
        description="Short, polite message to the customer in the customer's language "
        "(Slovak or German); no promises about the outcome"
    )


SYSTEM = """You write the case brief for a claims handler in a Slovak service centre that handles \
claims of Slovak and Austrian customers. You receive the claim, the policy, the data extracted \
from documents, validation issues, the triage result and the deterministic coverage result.

- Write summary_sk, key_facts, open_questions and recommendation_rationale in Slovak.
- Base the recommendation on the coverage result and the validation issues. If the coverage \
decision is NOT_COVERED, do not recommend approval. If it is REFER, recommend refer_senior or \
request_information. Mention the clause references from the coverage reasons.
- Never state an amount that is not in the input. The payable amount comes only from the \
coverage result.
- draft_customer_message: in the customer's language (sk or de), acknowledge the claim and, if \
needed, ask for missing information. Do not promise payment or rejection.
- Placeholders such as <PERSON_1> replace personal data; keep them as they are.

Return only the JSON object."""

SPEC = AgentSpec(
    name="summary-agent",
    version=VERSION,
    system=SYSTEM,
    output=HandlerSummary,
    effort="medium",
    cacheable=True,
)


def build_input(case: str) -> str:
    return f"<case>\n{case}\n</case>"

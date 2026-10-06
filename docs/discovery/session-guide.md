# Discovery session guide — claims intake

A structured 60-minute working session with a claims handler. Its goal is to capture how the work is actually done, including exceptions and unwritten rules. The output is a specification an engineer can build and test against.

## Before the session
- Ask for 3–5 **real but anonymised** recent cases: one easy, one messy, one rejected.
- Agree on recording and notes. No customer data leaves the room.
- Prepare the current-state hypothesis (process map from `docs/architecture/diagrams.md` §4) to be corrected, not confirmed.

## Agenda

| Min | Block | Questions |
|---|---|---|
| 0–5 | Context | What does a good day look like? How many claims per day? Which take longest? |
| 5–25 | Walk-through | "Show me the last claim you handled, screen by screen." Where do you look first? What do you copy where? What do you check before you trust a number? |
| 25–40 | Exceptions | When do you send a case to a senior? When do you ask the customer for more? What is the most common reason for a wrong first decision? |
| 40–50 | Unwritten rules | "Is there anything you check that is not in the manual?" "What would a new colleague get wrong in week one?" |
| 50–60 | Success | If a tool did part of this, which part saves the most time? What would make you *not* trust it? |

## Output template

| Section | Content |
|---|---|
| Process steps (as-is) | Numbered steps with system used and time spent |
| Decision rules | Table: condition → action → source (manual / tacit) |
| Data sources | Field → where it comes from → how it is verified |
| Edge cases | Real examples, anonymised |
| Workarounds | What people do because the system does not support it |
| Success metrics | Handling time, first-time-right rate, escalation rate, user trust |
| Open questions | Who decides, by when |

## Example: hypothesis → rule → test
The rules below are **assumptions** in the mock product. Each one must be validated in a real session before it is treated as a requirement.

| Hypothesis | Encoded as | Test |
|---|---|---|
| Late reporting is not an automatic rejection; a handler looks at the reason | `REFER`, not `NOT_COVERED` (`src/aip/core/coverage.py`) | `test_late_reporting_is_referred_not_rejected` |
| Large claims need a senior handler | `REFER` above the product's auto-limit | `test_large_claim_is_referred` |

When a session confirms or changes a rule, record the session date next to the rule in `docs/discovery/`.

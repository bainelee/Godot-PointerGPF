# V2 Natural-Language Boundary Principles

This document defines the intended product boundary for GPF V2 natural-language interaction.

It is not a statement that GPF should reject natural language.
It is a statement that GPF should use natural language as a bounded convenience layer on top of explicit tool behavior.

## Core Position

GPF is a tool with:

- explicit scope
- explicit workflows
- explicit side effects

Natural-language interaction is a usability advantage.
It is not a reason to expand GPF into an open-ended "understand everything" system.

The current product direction should remain:

- bounded
- testable
- documented
- predictable

not:

- open-domain
- infinitely paraphrase-tolerant
- behaviorally ambiguous

## Product Rule

For V2, natural language should be treated as:

- a thin request layer over explicit tool entrypoints

not as:

- a separate product goal that tries to absorb arbitrary user intent

That means the system should prefer:

- a small set of documented request shapes
- stable routing
- visible refusal or clarification when the request falls outside the supported boundary

and should avoid:

- continuously expanding phrase lists without product justification
- interpreting broad requests as permission for multi-step hidden orchestration
- silently taking high-impact actions because a vague sentence sounded similar to a supported phrase

## Development Constraints

When extending natural-language support in V2, follow these constraints:

1. Add support only for high-frequency, product-relevant user requests.
2. Prefer explicit, narrow request shapes over broad free-form paraphrase coverage.
3. Keep one request mapped to one primary user goal.
4. Do not expand phrase matching merely to make the system feel more "smart".
5. Do not hide multi-step execution behind vague user language.
6. Treat unsupported requests as normal product boundary cases, not as failures to be patched away immediately.

## Required Expansion Order

When adding a new natural-language request shape, do it in this order:

1. define the user-facing request shape and boundary in documentation
2. add tests for the supported and unsupported forms
3. add or update the planner / handler implementation
4. expose the supported request shape through the machine-readable guide when relevant

This order is required because the user contract should exist before the phrase matcher grows.

## What Counts As Good Natural-Language Support

Good support means:

- the user can learn a small number of effective ways to command GPF
- the system behaves consistently for those request shapes
- unsupported requests fail clearly and safely
- product behavior remains explainable from docs and tests

Good support does not mean:

- any vaguely related sentence is accepted
- every paraphrase is treated as equal
- the system guesses hidden goals from broad engineering requests

## Refusal And Clarification Principle

When a request is too broad, the system should prefer one of these outcomes:

- return no supported plan
- ask for the missing concrete input
- suggest one of the documented request shapes

It should not:

- invent a wide execution plan
- silently chain multiple tools
- treat ambiguity as permission

## Scope Discipline

Natural-language support should grow only when it improves one of these:

- first-use clarity
- high-frequency command ergonomics
- reduction of repeated user phrasing friction

It should not grow just because the model is technically capable of matching more text.

## Relationship To Existing V2 Work

The current V2 pieces that already fit this principle are:

- [v2-how-to-command-gpf.md](/D:/AI/pointer_gpf/docs/v2-how-to-command-gpf.md)
- `get_user_request_command_guide`
- `plan_user_request`
- `handle_user_request`

These pieces should continue to evolve as a bounded command layer, not as an open-ended NL router.

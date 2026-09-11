# RedPath learning library

The learning layer converts normalized findings into short beginner explanations. It uses a small reviewed local corpus and deterministic keyword matching. Every explanation keeps the finding ID, evidence state, original evidence source, and the IDs of any learning notes it used.

Evidence labels are not upgraded by this layer. `observed` stays observed, `inferred` stays inferred, and `verified` stays verified. A missing or unmatched finding produces an explicit missing-evidence message rather than a guessed claim.

The public integration functions are:

- `redpath_ai.learning.retrieve_notes(query, limit=3)` for bounded local retrieval.
- `redpath_ai.learning.explain_findings(findings)` for a `LearningResponse`.

The response always sets `execution_authorized` to `false`. This package has no command runner, network client, policy approval, or execution interface. Starter notes are versioned by stable source IDs in `redpath_ai/learning.py`; changes to their security meaning should be reviewed like code.

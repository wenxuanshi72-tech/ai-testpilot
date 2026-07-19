This is the single bounded recovery attempt for a batch that previously failed strict schema
validation. Regenerate the batch from the supplied PRD_DATA; do not refer to earlier output.

The root object must contain exactly these fields and no others: batch_id, source_sections,
requirements, reported_count, batch_complete. Each requirement must contain exactly these fields
and no others: requirement_id, title, description, requirement_type, source_section,
source_excerpt, acceptance_criteria, business_rules, actors, priority, risk_level, ambiguities,
dependencies, testability, confidence, tags.

Use only these enum values:
- requirement_type: functional, business_rule, security, privacy, quality
- priority: must, should, could
- risk_level: low, medium, high, critical
- testability: testable, partially_testable, not_testable

Use uppercase IDs matching REQ-[A-Z0-9][A-Z0-9-]{2,79}. Copy batch_id and source_sections exactly
from the request. source_section must be one of those exact strings. source_excerpt must be a
verbatim continuous excerpt from PRD_DATA. All list items must be unique strings; dependencies
must contain only requirement IDs produced in this batch, or be empty. confidence must be a number
from 0 through 1. reported_count must equal the requirements array length and batch_complete must
be true. Return only the JSON object.

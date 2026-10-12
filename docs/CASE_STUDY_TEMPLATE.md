# InvoiceAI — From messy documents to validated accounting records

> Replace every bracketed placeholder with verified facts. Do not publish fabricated metrics or imply a customer deployment that did not happen.

## Problem
[Who had the problem? What did the manual workflow look like? How many documents and how much time were measured?]

## Constraints and requirements
- Inputs: [PDF / scan / email formats observed]
- Required fields: [list]
- Business rules: [list]
- Privacy and access requirements: [list]
- Existing system: [accounting platform and sandbox/test status]

## Architecture
[Insert a diagram and explain ingestion, extraction, deterministic validation, review queue, persistence and external sync.]

## Evaluation method
- Dataset(s) and versions: [SROIE / CORD / invoice-specific / consented pilot]
- Number of documents: [N]
- Ground-truth method: [who labelled and how disagreements were resolved]
- Split policy: [avoid leakage between tuning and final evaluation]
- Normalization: [document exact-match and field-level rules]

## Results
| Metric | Baseline | Final | Evidence |
|---|---:|---:|---|
| Vendor-name accuracy | [ ] | [ ] | [report link] |
| Invoice-number accuracy | [ ] | [ ] | [report link] |
| Total accuracy | [ ] | [ ] | [report link] |
| Document exact-match | [ ] | [ ] | [report link] |
| Auto-approval coverage | [ ] | [ ] | [threshold report] |
| Incorrect auto-approvals | [ ] | [ ] | [threshold report] |
| Median manual review time | [ ] | [ ] | [timing protocol] |
| End-to-end processing time | [ ] | [ ] | [logs] |

## Failure analysis
1. [Failure class] → [root cause] → [change] → [regression test]
2. [Failure class] → [root cause] → [change] → [regression test]
3. [Failure class] → [root cause] → [change] → [regression test]

## Human-in-the-loop and safety
[Explain which cases are routed to reviewers, who can approve, how changes are audited, how thresholds were chosen, and why LLM self-confidence is not treated as calibrated probability.]

## Integration reliability
[Sandbox/provider, test environment, successful create/read round-trip, duplicate handling, retry behavior, failure handling. State explicitly if integration was not tested.]

## Trade-offs
[Why this OCR/parser/model/database/workflow? What did you intentionally not build?]

## Customer/pilot evidence
[Only include with permission. Describe role, anonymized workflow, consent, sample size and feedback.]

## What I would do next
[Production authentication, tenant isolation, data retention, monitoring, queue workers, more representative benchmark.]

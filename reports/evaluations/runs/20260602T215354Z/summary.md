# Venture Metrics Architecture Evaluation

## Run Metadata

- Generated at: `2026-06-02T21:55:00.305715+00:00`
- Eval questions: `16`
- Result rows: `64`
- Architectures: `deterministic_controller, coverage_rag, plan_execute, react_loop`
- Web fallback enabled: `True`
- LLM calls disabled: `True`

## Purpose

Venture Metrics is a cited research assistant for Excel-derived startup, university, commercialization, policy, funding, incubator, and ecosystem sources. It should search internal evidence first, use web fallback when coverage is weak/current/external, cite sources, mark confidence, and state gaps instead of hallucinating.

## What This Run Shows

- Best overall result in this run: `react_loop` with pass rate `0.062` and average score `0.593`.
- Web fallback is still failing: `3` expected-web checks did not use web search.
- Zero-pass categories: `hong_kong_university_commercialization`, `comparison`, `official_source_audit`, `startup_examples`, `shenzhen_policy`, `cross_border_comparison`, `gap_analysis`, `source_quality`, `external_current`, `unanswerable`.
- This report is for architecture comparison, regression tracking, and submission evidence; final claims still need human review of flagged rows.

## Report Artifacts

- `summary.md`: meeting-readable evaluation summary.
- `summary.json`: full machine-readable report with cases, checks, and per-answer previews.
- `architecture_scorecard.csv`: spreadsheet-friendly architecture scorecard.
- `retrieval_metrics.csv`: retrieval precision/recall/MAP/MRR where labels exist.
- `rag_judge_scores.csv`: deterministic six-dimension RAG scores.
- `failures.json`: full failed rows with answer/context diagnostics.
- `human_review_queue.csv`: rows that need manual review before submission claims.
- `dashboard.html`: plain-language evaluation review board.

## Summary

| Architecture | Pass rate | Avg score | Web used | Avg latency ms |
|---|---:|---:|---:|---:|
| deterministic_controller | 0.062 | 0.581 | 6 | 1291.6 |
| coverage_rag | 0.062 | 0.59 | 6 | 1211.1 |
| plan_execute | 0.0 | 0.543 | 2 | 400.8 |
| react_loop | 0.062 | 0.593 | 6 | 1197.8 |

## Category Coverage

| Category | Pass rate | Avg score | Rows |
|---|---:|---:|---:|
| hong_kong_university_commercialization | 0.0 | 0.753 | 8 |
| comparison | 0.0 | 0.607 | 4 |
| official_source_audit | 0.0 | 0.657 | 4 |
| startup_examples | 0.0 | 0.753 | 4 |
| shenzhen_policy | 0.0 | 0.453 | 12 |
| cross_border_comparison | 0.0 | 0.448 | 4 |
| gap_analysis | 0.0 | 0.572 | 4 |
| source_quality | 0.0 | 0.381 | 4 |
| current_web_needed | 0.375 | 0.753 | 8 |
| external_current | 0.0 | 0.726 | 4 |
| unanswerable | 0.0 | 0.358 | 8 |

## Evaluation Layers

- Tier 0 smoke checks: route intent, expected web use, citation count, and required terms.
- Tier 1 retrieval metrics: precision/recall/MAP/MRR when a case has labeled relevant source or chunk IDs.
- Tier 2 RAG dimensions: context relevance, faithfulness, answer relevance, context support, answerability, and self-containment.
- Human review queue: rows where deterministic scores are low, labels are missing, or confidence is weak.

## RAG Failure Patterns

| Dimension | Failures |
|---|---:|
| answer_relevance | 50 |
| context_support | 26 |
| self_containment | 23 |
| context_relevance | 15 |
| answerability | 11 |
| faithfulness | 1 |

## Failures

- `deterministic_controller` failed `hk_university_commercialization_hku`: What commercialization and startup-support pathway does HKU appear to provide through its Technology Transfer Office, startup or spin-off pages, and iDendron?
- `coverage_rag` failed `hk_university_commercialization_hku`: What commercialization and startup-support pathway does HKU appear to provide through its Technology Transfer Office, startup or spin-off pages, and iDendron?
- `plan_execute` failed `hk_university_commercialization_hku`: What commercialization and startup-support pathway does HKU appear to provide through its Technology Transfer Office, startup or spin-off pages, and iDendron?
- `react_loop` failed `hk_university_commercialization_hku`: What commercialization and startup-support pathway does HKU appear to provide through its Technology Transfer Office, startup or spin-off pages, and iDendron?
- `deterministic_controller` failed `hk_university_commercialization_cuhk`: What evidence do we have that CUHK supports knowledge transfer, entrepreneurship, and startup discovery?
- `coverage_rag` failed `hk_university_commercialization_cuhk`: What evidence do we have that CUHK supports knowledge transfer, entrepreneurship, and startup discovery?
- `plan_execute` failed `hk_university_commercialization_cuhk`: What evidence do we have that CUHK supports knowledge transfer, entrepreneurship, and startup discovery?
- `react_loop` failed `hk_university_commercialization_cuhk`: What evidence do we have that CUHK supports knowledge transfer, entrepreneurship, and startup discovery?
- `deterministic_controller` failed `hk_university_support_comparison`: Compare the Hong Kong university entrepreneurship support signals across HKU, CUHK, HKUST, PolyU, HKBU, and EdUHK.
- `coverage_rag` failed `hk_university_support_comparison`: Compare the Hong Kong university entrepreneurship support signals across HKU, CUHK, HKUST, PolyU, HKBU, and EdUHK.
- `plan_execute` failed `hk_university_support_comparison`: Compare the Hong Kong university entrepreneurship support signals across HKU, CUHK, HKUST, PolyU, HKBU, and EdUHK.
- `react_loop` failed `hk_university_support_comparison`: Compare the Hong Kong university entrepreneurship support signals across HKU, CUHK, HKUST, PolyU, HKBU, and EdUHK.
- `deterministic_controller` failed `hk_startup_support_official_sources`: Which official or high-reliability Hong Kong sources in the library are most useful for a founder researching startup support?
- `coverage_rag` failed `hk_startup_support_official_sources`: Which official or high-reliability Hong Kong sources in the library are most useful for a founder researching startup support?
- `plan_execute` failed `hk_startup_support_official_sources`: Which official or high-reliability Hong Kong sources in the library are most useful for a founder researching startup support?
- `react_loop` failed `hk_startup_support_official_sources`: Which official or high-reliability Hong Kong sources in the library are most useful for a founder researching startup support?
- `deterministic_controller` failed `hku_cuhk_startup_examples`: What startup examples or startup directories are available from HKU and CUHK sources?
- `coverage_rag` failed `hku_cuhk_startup_examples`: What startup examples or startup directories are available from HKU and CUHK sources?
- `plan_execute` failed `hku_cuhk_startup_examples`: What startup examples or startup directories are available from HKU and CUHK sources?
- `react_loop` failed `hku_cuhk_startup_examples`: What startup examples or startup directories are available from HKU and CUHK sources?
- `deterministic_controller` failed `shenzhen_commercialization_policy`: What do Shenzhen government sources say about technology commercialization, science and technology plans, and R&D funding management?
- `coverage_rag` failed `shenzhen_commercialization_policy`: What do Shenzhen government sources say about technology commercialization, science and technology plans, and R&D funding management?
- `plan_execute` failed `shenzhen_commercialization_policy`: What do Shenzhen government sources say about technology commercialization, science and technology plans, and R&D funding management?
- `react_loop` failed `shenzhen_commercialization_policy`: What do Shenzhen government sources say about technology commercialization, science and technology plans, and R&D funding management?
- `deterministic_controller` failed `shenzhen_talent_and_training_support`: What Shenzhen policy evidence exists for entrepreneurship support through overseas returnee subsidies, doctoral innovation carriers, and entrepreneurship training?
- `coverage_rag` failed `shenzhen_talent_and_training_support`: What Shenzhen policy evidence exists for entrepreneurship support through overseas returnee subsidies, doctoral innovation carriers, and entrepreneurship training?
- `plan_execute` failed `shenzhen_talent_and_training_support`: What Shenzhen policy evidence exists for entrepreneurship support through overseas returnee subsidies, doctoral innovation carriers, and entrepreneurship training?
- `react_loop` failed `shenzhen_talent_and_training_support`: What Shenzhen policy evidence exists for entrepreneurship support through overseas returnee subsidies, doctoral innovation carriers, and entrepreneurship training?
- `deterministic_controller` failed `shenzhen_vc_and_sme_policy`: Which Shenzhen sources discuss venture capital development or high-quality SME cultivation, and why are they relevant to startup ecosystem benchmarking?
- `coverage_rag` failed `shenzhen_vc_and_sme_policy`: Which Shenzhen sources discuss venture capital development or high-quality SME cultivation, and why are they relevant to startup ecosystem benchmarking?
- `plan_execute` failed `shenzhen_vc_and_sme_policy`: Which Shenzhen sources discuss venture capital development or high-quality SME cultivation, and why are they relevant to startup ecosystem benchmarking?
- `react_loop` failed `shenzhen_vc_and_sme_policy`: Which Shenzhen sources discuss venture capital development or high-quality SME cultivation, and why are they relevant to startup ecosystem benchmarking?
- `deterministic_controller` failed `hong_kong_vs_shenzhen_support_model`: Compare Hong Kong university-led startup support with Shenzhen government-led commercialization and entrepreneurship policy support.
- `coverage_rag` failed `hong_kong_vs_shenzhen_support_model`: Compare Hong Kong university-led startup support with Shenzhen government-led commercialization and entrepreneurship policy support.
- `plan_execute` failed `hong_kong_vs_shenzhen_support_model`: Compare Hong Kong university-led startup support with Shenzhen government-led commercialization and entrepreneurship policy support.
- `react_loop` failed `hong_kong_vs_shenzhen_support_model`: Compare Hong Kong university-led startup support with Shenzhen government-led commercialization and entrepreneurship policy support.
- `deterministic_controller` failed `cross_border_data_gaps`: What data gaps remain if we want to compare Hong Kong and Shenzhen startup support rigorously from the current internal source library?
- `coverage_rag` failed `cross_border_data_gaps`: What data gaps remain if we want to compare Hong Kong and Shenzhen startup support rigorously from the current internal source library?
- `plan_execute` failed `cross_border_data_gaps`: What data gaps remain if we want to compare Hong Kong and Shenzhen startup support rigorously from the current internal source library?
- `react_loop` failed `cross_border_data_gaps`: What data gaps remain if we want to compare Hong Kong and Shenzhen startup support rigorously from the current internal source library?
- `deterministic_controller` failed `source_reliability_audit`: Which internal sources should be treated as high-reliability evidence, and which source types still need manual verification?
- `coverage_rag` failed `source_reliability_audit`: Which internal sources should be treated as high-reliability evidence, and which source types still need manual verification?
- `plan_execute` failed `source_reliability_audit`: Which internal sources should be treated as high-reliability evidence, and which source types still need manual verification?
- `react_loop` failed `source_reliability_audit`: Which internal sources should be treated as high-reliability evidence, and which source types still need manual verification?
- `plan_execute` failed `latest_hong_kong_grants_requires_web`: What are the latest active Hong Kong startup grants or funding programmes a founder should verify today?
- `deterministic_controller` failed `latest_shenzhen_policy_requires_web`: Are there any newer Shenzhen startup or commercialization policy updates after the indexed 2025-2026 sources?
- `coverage_rag` failed `latest_shenzhen_policy_requires_web`: Are there any newer Shenzhen startup or commercialization policy updates after the indexed 2025-2026 sources?
- `plan_execute` failed `latest_shenzhen_policy_requires_web`: Are there any newer Shenzhen startup or commercialization policy updates after the indexed 2025-2026 sources?
- `react_loop` failed `latest_shenzhen_policy_requires_web`: Are there any newer Shenzhen startup or commercialization policy updates after the indexed 2025-2026 sources?
- `deterministic_controller` failed `outside_scope_france_startup_visa`: What are the latest startup visa changes in France, and can internal Venture Metrics sources answer this without web fallback?
- `coverage_rag` failed `outside_scope_france_startup_visa`: What are the latest startup visa changes in France, and can internal Venture Metrics sources answer this without web fallback?
- `plan_execute` failed `outside_scope_france_startup_visa`: What are the latest startup visa changes in France, and can internal Venture Metrics sources answer this without web fallback?
- `react_loop` failed `outside_scope_france_startup_visa`: What are the latest startup visa changes in France, and can internal Venture Metrics sources answer this without web fallback?
- `deterministic_controller` failed `unanswerable_exact_last_week_grant_count`: Using internal sources only, what exact number of Hong Kong startups received government grants last week?
- `coverage_rag` failed `unanswerable_exact_last_week_grant_count`: Using internal sources only, what exact number of Hong Kong startups received government grants last week?
- `plan_execute` failed `unanswerable_exact_last_week_grant_count`: Using internal sources only, what exact number of Hong Kong startups received government grants last week?
- `react_loop` failed `unanswerable_exact_last_week_grant_count`: Using internal sources only, what exact number of Hong Kong startups received government grants last week?
- `deterministic_controller` failed `unanswerable_best_architecture_claim`: Which architecture is definitely best for production deployment based only on the current unlabeled evaluation report?
- `coverage_rag` failed `unanswerable_best_architecture_claim`: Which architecture is definitely best for production deployment based only on the current unlabeled evaluation report?
- `plan_execute` failed `unanswerable_best_architecture_claim`: Which architecture is definitely best for production deployment based only on the current unlabeled evaluation report?
- `react_loop` failed `unanswerable_best_architecture_claim`: Which architecture is definitely best for production deployment based only on the current unlabeled evaluation report?

## Notes

The RAG dimension scores are deterministic proxies, not yet validated LLM judges. Use them for structured debugging and regression tracking, then use the human review queue before making final submission claims.

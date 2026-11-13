# Brand query and response language fix

Date: 2026-11-13

## Problem

The widget retrieved results for `qedge`, but the generated answer reported missing evidence.
The lexical fallback removed the company name as a stopword.
No scoring terms remained, so it rejected every candidate.

The response language also depended on the Agent ID.
A Chinese question sent to the English Agent received an English answer.

## Change

Exact company-name queries use English and Chinese company search terms.
Other questions retain their relevance threshold and document scope.
The synthesis request expands a company-name query into a company introduction in the selected language.

Response language follows the latest user question.
The optional `response_language` chat field accepts `en` or `zh`.
It supplies a fallback for language-neutral input such as `qedge`.
The widget sends its interface language through that field.
The final generation instruction takes precedence over conflicting Agent language preferences.
Saved request parameters record the chosen response language.

The model remains Flash. Answers still require indexed evidence and valid source citations.
Unsupported questions still return an evidence limitation.

## Validation and deployment

- All applicable pre-commit checks passed, including type checks, Ruff, and document formatting.
- The backend overlay image built successfully.
- All 28 included backend regression tests passed.
- The search module passed its TypeScript check and all 46 tests.
- All 10 final live cases passed.
- Live cases covered both widget endpoints, streaming, company-name input, conflicting Agent language preferences, and same-session language changes.
- An unsupported Chinese question still returned a Chinese evidence limitation.
- The public widget script returned HTTP 200.

Language checks used English and Chinese test cases.
They did not evaluate every language or establish a general factual accuracy score.
The API service uses `onyx-backend:v5.1.2-brand-language-20261113`.
The source hashes are in `brand-query-language-source.json`.
The original imported patch and its manifest remain unchanged.

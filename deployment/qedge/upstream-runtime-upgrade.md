# QEdge shared-runtime migration

This upgrade starts from QEdge `dev` at `312312425602fbc886c3bdca09a35baef0aea2b7`.
It merges official code at `56750c9e292ef660776636a8473a21242ee78763`.
The original deployment patch and manifests remain unchanged.

The requirements come from the owner's [Beta repair conversation](https://chatgpt.com/s/cx_6af7b55001748191bd029cf2dc79d21c).

## Preserved behavior

- Ordinary and deep knowledge questions use the configured Flash model.
- Answers summarize indexed evidence and contain checked source citations.
- Missing evidence makes no generation call. Summary failures ask the user to retry.
- Each turn retrieves fresh, authorized evidence. Previous answers are not evidence.
- Follow-ups use prior user questions only to resolve context.
- Brand-only queries retrieve company information with English and Chinese terms.
- The latest question sets the answer language. Brand-only queries can use `response_language`.
- Agent language preferences cannot override the question language.
- Document Set, source and ACL filters remain in the shared search pipeline.
- Attachments, Projects, incognito and multi-model requests retain the standard route.
- Knowledge answers use the shared Stop, delivery, persistence and replay mechanisms.

`KnowledgeAgent` records a fixed search call without a provider request.
It then uses the configured client for one evidence-only synthesis call.
The shared runtime saves both steps and their typed source details.
Its restoration state identifies the knowledge route explicitly.
Messages received during synthesis stay pending for a subsequent turn.

When speaking for QEdge, the synthesis prompt requests first-person language.
The prompt still forbids unsupported claims.

## Other repositories

The shared conversation also describes Search widget changes, including its unified
entry, theme, animation, floating-button spacing, layering and corner clipping.
Those changes belong to `Qedge-Group/qedge-one-search` and are outside this Onyx merge.
Its conversation records merged prototype work through PR 7.
This migration does not modify that repository or replace the Beta deployment.
The owner excluded `codex/rag-quality-14b`; this migration does not use it.

## Validation

```sh
PYTHONPATH=backend uv run python -m unittest test_knowledge_rag
uv run pytest backend/tests/unit/onyx/chat/test_knowledge_agent.py
```

Use a complete build of this branch for deployment. The archived v5.1.2 overlay
Dockerfile is not compatible with this runtime migration.
Live Starter, same-session language switching, API and widget checks require a
running stack with the configured Flash provider and indexed documents.

# QEdge Beta RAG customization

The original deployment snapshot is commit `1ea2c7b96e574b1a4d4aa81feaf1b7162a2dee65`.
It uses Onyx v5.1.2 as its base.

The original patch and `source-provenance.json` describe that immutable snapshot.
Later fixes have separate source manifests and Git commits.
See [the brand-query and language fix](brand-query-language-fix.md) for the current release.

## Build

Run from the repository root:

```sh
docker build -f deployment/qedge/Dockerfile.rag-stable -t onyx-backend:v5.1.2-brand-language-20261113 .
```

The Dockerfile copies ten changed backend modules onto the v5.1.2 backend image.
Set the `ONYX_BASE_IMAGE` build argument to use an approved image digest.

Read `documentation/admins/managing_features/rag_and_search.mdx` for the custom route.
The environment templates document its settings.
Provider credentials and Agent IDs remain deployment configuration.
This repository does not contain runtime secrets or host-specific Compose overrides.

## Validate

With the repository dependencies installed, run:

```sh
PYTHONPATH=backend uv run python -m unittest test_knowledge_rag
```

## Original patch

`patches/onyx-v5.1.2-rag-summary.patch` is the exact downloaded server patch.
Its SHA-256 is `ae5c92301897de4f78af87642d5c81b31554ccb1eb773d5f21c034933b2beaba`.
Apply it only to a clean checkout of baseline commit `6b627422c711802fee78b89dda3e25ca0f48ec7e`.
Do not apply it again on a branch that already contains the customization.

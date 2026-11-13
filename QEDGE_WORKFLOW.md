# QEdge branch workflow

This policy is required for QEdge changes.

## Branch roles

- Onyx `main` mirrors `onyx-dot-app/onyx:main`. Do not add QEdge commits to `main`.
- `dev` is the integration branch for QEdge customization.
- Create every new feature, fix, documentation, and upgrade branch from current `origin/dev`.
- Open pull requests against `dev`. After checks pass, merge them into `dev`.
- Do not commit or push directly to `dev` during normal development.
- Do not reset, force-push, or delete shared or archive branches.
- The Search repository has no external official upstream. Its `main` remains a release branch; custom development still starts from `dev`.

## Start work

```sh
git fetch origin main dev
git switch dev
git pull --ff-only origin dev
git switch -c fix/descriptive-name
```

Check the active branch and base before edits or remote writes.
If the branch started from `main` or another feature branch, move the work onto a branch from `dev`.
Do not silently continue on the wrong base.

## Integrate work

Run the checks for the changed files.
Open a pull request with base `dev`.
Update the working branch with current `dev` before merge.
Use a merge commit to retain branch history.

## Update official code

Sync Onyx `main` from the official upstream without adding custom commits.
This does not deploy code or update `dev`.
Start an `upgrade/*` branch from `dev` for an upstream version change.
Resolve the custom changes there, run regression checks, and merge into `dev`.
Do not automatically rebase custom branches onto official `main`.

## Initial integration baseline

Onyx `dev` starts at `fe071cfc385c19e528a700b839295779c4865fb9`.
It includes the complete Beta snapshot `1ea2c7b96e574b1a4d4aa81feaf1b7162a2dee65` and the brand-query/language fix.
Search `dev` starts at `aa60fac6c7e5fce1767f0d5d9f21f76068371f10`.
It includes the archive branch and its widget language fix.
The legacy `codex/rag-quality-14b` branch is excluded at the owner's request.
The deployed Onyx baseline remains v5.1.2. Initializing `dev` does not merge unreleased official `main`.

## Enforcement

`AGENTS.md` makes this workflow mandatory for coding agents.
The QEdge PR workflow rejects custom pull requests into `main` and checks that feature branches contain current `dev`.
Repository administrators must require pull requests and the QEdge workflow on `dev` to prevent bypass by direct push.
The connected GitHub tool cannot configure repository protection.
Do not claim that branch protection is enabled unless its settings were verified.

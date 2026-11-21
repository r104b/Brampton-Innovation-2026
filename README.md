# SentraContext master

This repository owns the shared context engine. Each fictional client has its
own private GitHub repository containing a versioned agent kit, client manifest,
and only that client's context and product code.

Gmail -> authenticated master API -> trusted client routing -> structured AI
extraction -> evidence-backed Supabase state -> client-specific kit/context PR
-> review and merge -> fresh coding-agent session in that client's repository.

Read [the architecture and setup guide](docs/CLIENT_REPOSITORIES.md) first.
It supersedes the earlier single-repository deployment plan. The design follows
the supplied Challenge 8 briefs: retain completed work, surface open questions,
preserve evidence, and support more than one coding agent. The separate-repo
layout is the team's chosen design. This is a sample-data prototype.

## Start locally

```sh
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Before ingestion, apply migration 002 and the fictional routing seed after the
original migration/seed, and configure the process environment as described in
`.env.example` and the architecture guide. Supabase is authoritative for customers,
projects, and branch/path mappings. The seed contains placeholder GitHub names
and must be edited. Gmail setup is in
[gmail/README.md](gmail/README.md). The health endpoint is `/health`.

## Publish client context

```sh
python -m backend.services.context_export --project-id maple-grove-demo --output-root local-exports
python -m backend.services.github_sync --project-id maple-grove-demo
```

The publisher reads Supabase, builds the shared kit and client-specific state,
and opens a PR in the registered private client repository. Use `--provision`
only for explicit client onboarding. With `CLIENT_SYNC_ENABLED=true`, ingestion
also attempts publication in the background. The master scheduled workflow
retries all configured clients every 15 minutes when enabled. Nothing merges
PRs automatically. Each content version can have its own PR; review the latest
version and close older proposals. Multiple projects per customer and
multiple mapped destinations per project are supported. Ambiguous messages are
captured for identification review; scoped reviewers can split extracted items
across projects while retaining the same immutable source and evidence links.

## Offline checks

```sh
python -m pip install -r .github/ci/requirements.txt
python -m pytest tests -q -p no:cacheprovider
python -m ruff check --config .github/ci/ruff.toml backend tests agent-kit
```

The original `context/CURRENT_STATE.md` remains a synthetic test artifact in
this master repo. It is not a combined client directory. Generate it with:

```sh
python -m backend.services.context_generator --input sample-data/project-state.json --output context/CURRENT_STATE.md --fixture
```

Live Gmail forwarding, Supabase configuration, private repository creation, and
PR publication require team-owned test credentials. Offline tests do not prove
those external integrations. Historical date queries and deployment of arbitrary
business agents are outside the implemented context-recovery service.

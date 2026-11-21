# Current integration

Use [the customer/project routing guide](../docs/CLIENT_REPOSITORIES.md).
Supabase is authoritative for customer, project, and destination mappings.

Preview a validated project bundle with:

```sh
python -m backend.services.context_export --project-id maple-grove-demo --output-root local-exports
```

Publish mapped PRs when configured with:

```sh
python -m backend.services.github_sync --project-id maple-grove-demo
```

Generation targets registered project folders in separate private customer
repositories. The master snapshot is an offline fixture, not a customer index.

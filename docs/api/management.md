---
title: "Management Commands"
---
Management commands are thin wrappers around the service layer: they parse arguments, call a
service, and report results. Business logic lives in `micboard/services/`, so a command can be
replaced by a task or an API call without behaviour changes.

Run any command through the project's `manage.py`:

```bash
uv run --no-sync python manage.py <command> --help
```

The generated [Management Commands reference](reference/management-commands.md) lists every
command class, its options, and a link to its source. See
[Configuration](../configuration.md) for the settings those commands read.

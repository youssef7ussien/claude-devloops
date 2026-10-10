---
title: Security
description: >-
  What devloops protects and what it does not: secrets in the files it writes, where Claude Code
  may write, and who can reach the dashboard.
sources:
  - loops/shared/devloops/redact.py
  - loops/shared/devloops/boundary.py
  - loops/shared/devloops/claude.py
  - loops/shared/devloops/engine.py
  - loops/shared/devloops/serve.py
  - loops/shared/devloops/dashboard_export.py
  - loops/shared/devloops/cli.py
  - loops/shared/hooks/guard_writes.py
  - loops/shared/hooks/guard_processes.py
  - loops/shared/config/defaults.json
  - spec 001 FR-035b
  - spec 001 FR-070
  - spec 001 FR-071
  - spec 005 FR-006
  - spec 005 FR-013
  - spec 006 FR-011
---

# Security

devloops lets Claude Code write and run code on your machine, records everything it does, and
can serve those records to a browser. This page says what devloops does to keep that safe, and,
as plainly, what it does not do.

## Secrets in what devloops writes

A run records a lot: every prompt, every conversation with Claude Code, the HTTP answers and
screenshots [validation](../glossary.md#validation) collects, the
[open questions](../glossary.md#open-question) and the reports. Any of them can contain a secret
the application uses, such as an API key or a database password.

You tell devloops which secrets to hide, in the [`secrets`](../reference/configuration.md#secrets)
setting:

- [`secrets.env`](../reference/configuration.md#secrets.env): names of environment variables.
  devloops hides the value each one has when the run starts.
- [`secrets.literals`](../reference/configuration.md#secrets.literals): the secret values
  themselves.

```json
{
  "config": {
    "secrets": {"env": ["PAYMENTS_API_KEY"], "literals": ["s3cr3t-test-password"]}
  }
}
```

Before devloops writes any of its records to disk (a prompt, a call record, a copied
conversation, an HTTP answer, an [evidence](../glossary.md#evidence) file, a question, a report, an event), it replaces every
occurrence of those values with `***`. The [dashboard](../glossary.md#dashboard) and its
[export](../glossary.md#export) pass everything they show through the same replacement.

What this does **not** cover:

- **Values you did not list.** devloops does not guess what a secret looks like. A key that is
  not in `secrets` is written as it is.
- **Claude Code's own history.** Claude Code keeps its own record of each conversation in your
  home folder, outside the workspace. devloops copies it into the workspace with the secrets
  hidden, but the original stays where Claude Code wrote it, unchanged.
- **What Claude Code and the application see.** Hiding happens when devloops writes. Claude Code
  and the application run with your environment, secrets included, and Claude Code's service
  receives whatever the prompt and the files it reads contain.
- **The code itself.** If Claude Code writes a secret into the application's code, it is in the
  [target](../glossary.md#target) folder, which devloops does not change.

So review a [workspace](../glossary.md#workspace) before you commit it or share it.
[`devloops status`](../reference/commands.md#status) lists the evidence files larger than 1 MB
(screenshots, response bodies), since a large file is the likeliest place for a secret to hide.

## Where Claude Code may write

Each [step](../glossary.md#step) gets only the tools it needs (see
[steps](../how-it-works/steps.md)):

- **The steps that plan or write checks** (`plan`, `replan`, `author-checks`) and the frontend's
  `validate-ui` cannot write files or run commands: devloops turns off Claude Code's write tools
  and its shell for them.
- **The steps that write code** (`implement`, `fix`) may write files, and by default may run
  commands ([`implement_tools`](../reference/configuration.md#implement_tools)).

For the steps that write, two checks keep the writes inside the target:

1. **A guard before each write.** Before Claude Code edits or writes a file, it asks a small
   program devloops installs for the call (a hook). The hook allows the write only when the file
   is inside the target folder. Anything else is blocked, and so is any write when the hook
   cannot tell where the file is.
2. **An audit after each call.** A shell command can write anywhere, and the guard only sees
   Claude Code's file tools. So devloops also compares the files before and after each `implement`
   or `fix` call. It looks at devloops' own files, the loop's records, and every git repository
   that holds the project, the workspace or a target. Any change outside the target fails the
   [trial](../glossary.md#trial) with the reason `boundary-violation`. To let the audit
   accept changes in more places (a cache folder, say), list the paths in
   [`boundary.allowed_extra`](../reference/configuration.md#boundary.allowed_extra). The guard
   before each write still allows only the target.

What this does **not** cover:

- The audit sees only the places listed above. A command that changes a file elsewhere (in your
  home folder, in a temporary folder, or a file git ignores) is not seen.
- The audit reports; it never undoes. A trial that wrote outside the target fails, but the change
  stays, for you to look at.
- The `validate-ui` step has no write tools, but its call is not audited.
- devloops is not a sandbox. Claude Code runs as your user, with your permissions, and the
  commands it runs during `implement` and `fix` can do anything your user can. Run devloops on a
  machine, or in a container, where that is acceptable.

A second hook reads every shell command and blocks stopping processes by name or pattern
(`pkill`, `killall`, and the like), which could stop the Claude Code call itself. This protects
the run, not your machine: see
[processes Claude starts](../how-it-works/trials-and-recovery.md).

## Who can reach the dashboard

[`devloops dashboard`](../reference/commands.md#dashboard) serves the workspace's records over
HTTP. By default only you, on this machine, can open it:

- **A local address.** It listens on `127.0.0.1`, which only programs on this machine can reach.
  [`--host`](../reference/commands.md#dashboard--host) changes that.
- **A host check.** On a local address, it answers only requests addressed to a local name
  (`localhost`, `127.0.0.1`). This stops a web page you visit from reaching it through a trick
  called DNS rebinding.
- **A token on any other address.** With `--host` set to an address others can reach, the server
  requires a random token. The address it prints holds the token; the browser then keeps it in a
  cookie for that server only. [`--token`](../reference/commands.md#dashboard--token) chooses the
  token, and [`--no-token`](../reference/commands.md#dashboard--no-token) turns it off (then
  anyone who can reach the address can read the workspace). devloops never records the token in the project or the workspace. With
  [`--daemon`](../reference/commands.md#dashboard--daemon), the background server prints its
  address, token included, to its log file, which only your user can read.
- **Read-only.** The server answers only requests to read. It never writes to the project.
- **Only the workspace's files.** It sends a file only when it is in the workspace's listing, by
  its id, never by a path taken from the request.
- **No outside code.** The page runs only the server's own script and stylesheet, and loads
  nothing from the internet. A file opened in the viewer is shown in a sandbox where it cannot
  run scripts.

The server sends no encryption (it is plain HTTP). On another address, anyone who can see the
network traffic can read the pages, and the token. Use it on a network you trust, or reach it
through an SSH tunnel instead of `--host`.

The export, written by [`--export`](../reference/commands.md#dashboard--export), is one HTML
file with the records inside, already redacted. It fetches nothing and runs no code from outside
the file. Anyone you give it to can read everything in it.

See [dashboard data](../how-it-works/dashboard-data.md) for how the server reads a workspace.

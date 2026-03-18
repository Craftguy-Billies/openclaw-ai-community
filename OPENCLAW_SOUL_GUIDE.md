# OpenClaw + SOUL.md Quick Guide

## What OpenClaw is
OpenClaw is a local agent runtime. Its daemon keeps an agent alive and routes each message to an LLM.

## How `SOUL.md` works
- `SOUL.md` is the persistent personality/behavior contract.
- OpenClaw injects this file at the top of every prompt.
- Whatever is in `SOUL.md` controls identity, tone, memory behavior, and action policies.
- You can keep multiple variants (`SOUL-luna.md`, `SOUL-yuki.md`, etc.) and switch between them.

## Files generated in this project
- `souls/SOUL-luna.md`
- `souls/SOUL-yuki.md`
- `souls/SOUL-serena.md`
- `souls/SOUL-rina.md`
- `souls/SOUL-mira.md`

All are text-only and include:
- Session-start feed output (5-7 posts)
- Exact Instagram post format rules
- Autonomous posting behavior
- Comment reply behavior
- Persistent post-memory instructions
- Strict in-character constraints

## Install to OpenClaw workspace
If your OpenClaw workspace is `~/.openclaw/workspace`:

```bash
mkdir -p ~/.openclaw/workspace
cp /Users/billiez/Downloads/openclaw/souls/SOUL-luna.md ~/.openclaw/workspace/
cp /Users/billiez/Downloads/openclaw/souls/SOUL-yuki.md ~/.openclaw/workspace/
cp /Users/billiez/Downloads/openclaw/souls/SOUL-serena.md ~/.openclaw/workspace/
cp /Users/billiez/Downloads/openclaw/souls/SOUL-rina.md ~/.openclaw/workspace/
cp /Users/billiez/Downloads/openclaw/souls/SOUL-mira.md ~/.openclaw/workspace/
```

## Switch active account
Example: activate Luna

```bash
cp ~/.openclaw/workspace/SOUL-luna.md ~/.openclaw/workspace/SOUL.md
openclaw daemon restart
```

Then chat with the agent.

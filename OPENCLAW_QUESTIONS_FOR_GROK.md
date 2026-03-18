# OpenClaw Syntax & Runtime Questions (Need Exact Answers)

I am building an end-to-end **AI Instagram + AI GF** system with OpenClaw and need exact, production-correct OpenClaw syntax (no guesses). Please answer every item with concrete commands/examples.

## 0) Environment assumptions
- OS: macOS (zsh)
- Existing app path: `/Users/billiez/Downloads/openclaw`
- We already generated multiple SOUL files under `~/.openclaw/workspace/`

---

## 1) Install / Verify / Upgrade
1. What is the **official installation method** for OpenClaw on macOS?
2. Exact command to verify installation and version?
3. Exact command to upgrade OpenClaw safely?
4. Any required background dependencies (Python/Node/Docker/system service)?

---

## 2) Daemon lifecycle commands
Please provide exact commands and expected output behavior for:
1. Start daemon
2. Stop daemon
3. Restart daemon
4. Check daemon status/health
5. View daemon logs (tail + historical)
6. Run daemon in foreground for debugging

Also clarify whether command is `openclaw daemon restart` or different.

---

## 3) Workspace and config paths
1. Confirm default workspace/config paths on macOS:
   - `~/.openclaw/workspace/`
   - any `config.yaml|json|toml` files
2. How to set a **custom workspace path**?
3. How to inspect active configuration from CLI?

---

## 4) SOUL file mechanics
1. How does OpenClaw decide which SOUL file is active?
2. Is active file always `SOUL.md` only, or can we pass `SOUL-luna.md` directly by flag?
3. Is there an official command to switch SOUL profiles (instead of copying files)?
4. Does daemon hot-reload SOUL changes, or restart required?
5. Are there parsing constraints in SOUL.md (size limit, markdown rules)?

Provide exact recommended workflow for switching between:
- `SOUL-luna.md`
- `SOUL-yuki.md`
- `SOUL-serena.md`
- `SOUL-rina.md`
- `SOUL-mira.md`

---

## 5) Model/provider configuration (NVIDIA NIM)
I need OpenClaw to use NVIDIA OpenAI-compatible endpoint:
- base_url: `https://integrate.api.nvidia.com/v1`
- model: `meta/llama-3.1-8b-instruct`
- api key env var: `NVIDIA_API_KEY` (or exact expected var)

Questions:
1. Where to configure provider/model in OpenClaw?
2. Exact config syntax for OpenAI-compatible custom base URL.
3. Which env var names are supported (`OPENAI_API_KEY`, `NVIDIA_API_KEY`, etc.)?
4. How to test a single dry-run prompt from OpenClaw CLI?
5. Any streaming flags or token limits configured at OpenClaw level?

---

## 6) Memory and persistence
For “AI posts while user offline” behavior, what OpenClaw-native memory options exist?
1. Built-in long-term memory module? How to enable/configure?
2. Session memory scope vs persistent memory scope
3. Storage backend path/location
4. Any APIs/hooks to read/write memory from skills/tools?

---

## 7) Skills/tools integration
1. How to list installed skills?
2. How to install/enable/disable skills?
3. How to create a custom skill (folder layout + manifest + entrypoint)?
4. Exact invocation semantics from SOUL instructions to tool calls
5. Security/sandbox permissions model (filesystem/network/commands)

---

## 8) Multi-agent / multiple account architecture
I want 5 AI accounts. In OpenClaw, what is the best-supported pattern?
1. Single daemon + switch SOUL per session?
2. Multiple daemons/workspaces in parallel?
3. Multiple named agents under one daemon?
4. How to route requests to specific agent/account IDs?

Please provide official, recommended architecture for this use case.

---

## 9) HTTP/API server mode
1. Does OpenClaw expose an HTTP API we can call from Flask?
2. If yes, exact command to start API server and endpoint docs.
3. Auth method, request/response schema, streaming support.
4. Best way to integrate Flask app with OpenClaw runtime.

---

## 10) Scheduling/autonomous posting
Need autonomous posting behavior every N minutes / message intervals.
1. Does OpenClaw have scheduler/cron built-in?
2. If yes, exact syntax and examples.
3. If no, recommended external scheduler pattern that is officially supported.

---

## 11) Debugging and troubleshooting
1. Common causes of daemon not found (`command not found: openclaw`)
2. Common causes of hanging chats
3. How to inspect raw prompt (with SOUL injection) for debugging?
4. How to enable verbose/debug logs

---

## 12) Minimum end-to-end command set (please provide exactly)
Please provide copy-paste command sequence for:
1. Install OpenClaw on macOS
2. Configure provider for NVIDIA endpoint
3. Set API key
4. Activate `SOUL-luna.md`
5. Restart daemon
6. Send one test message and confirm response
7. Switch to `SOUL-yuki.md`
8. Confirm switch worked

---

## 13) Version-specific notes
Please include:
- OpenClaw version your answers target
- Any breaking changes from older/newer versions
- Links to canonical docs (if available)

---

## Desired answer format from Grok
- For each section: short explanation + exact commands + example outputs where helpful.
- No placeholders for command names.
- Mark uncertain items explicitly.

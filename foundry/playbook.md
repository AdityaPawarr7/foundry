# Making an OSS Project Concentrate-Compatible — Agent Playbook

> **Copy this whole file onto the target VM and hand it to Claude Code (or paste it as a prompt).**
> It is written to be run by an AI agent from a fresh checkout of some open-source
> project (n8n, LibreChat, Dify, Flowise, LangFlow, an IDE plugin, etc.) with **zero
> prior context** about that project.
>
> **The golden rule: do NOT touch Concentrate until the software runs.** Phases are
> gated. Do not start a phase until the previous phase's exit criteria are met and
> the human has confirmed.

---

## What "Concentrate-compatible" means

[Concentrate.ai](https://concentrate.ai) is an **OpenAI-compatible LLM gateway**.
Making an OSS project compatible = letting a user point that project at Concentrate
as an LLM provider and have it just work.

Concentrate API facts (stable — assume these unless the API tells you otherwise):
- **Base URL:** `https://api.concentrate.ai/v1`
- **Auth:** `Authorization: Bearer <API_KEY>` header
- **Endpoints:** both `/v1/responses` (first-class, preferred) and
  `/v1/chat/completions` (fallback) work
- **`GET /v1/models`** lists available models (~150+)
- **Model names** look like `anthropic/claude-opus-4-8`, `gpt-5.4`, `claude-opus-4-6`,
  or the special value `auto`

Because it is OpenAI-compatible, "adding Concentrate" is almost always: *find where
the project configures an OpenAI/OpenAI-compatible provider, and add Concentrate as a
new option (base URL + Bearer key + model list)* — NOT writing a provider from scratch.

---

## Phase 0 — Recon (read-only, ~10 min)

**Goal:** understand the project before changing anything. Do not edit yet.

1. Identify the project: read `README.md`, `CONTRIBUTING.md`, `AGENTS.md`/`CLAUDE.md`,
   `package.json` / `pyproject.toml` / `go.mod` / `Cargo.toml` — whatever declares the
   toolchain and scripts.
2. Determine the stack, package manager, and Node/Python/Go version. **Use the exact
   versions the repo pins** (`.nvmrc`, `.tool-versions`, `engines`, `.python-version`).
   Mismatched runtime is the #1 cause of a failed first build.
3. Find how it's meant to be run: dev script, Docker compose, `make`, etc. Prefer
   **running from source** over Docker for iteration speed (faster rebuild loop), but
   Docker is fine if source setup is painful.
4. Find where LLM providers live. Grep for the seams:
   ```bash
   grep -rniE "openai|baseURL|base_url|api\.openai\.com|OPENAI_API_KEY|chat/completions|/v1/responses" \
     --include=*.ts --include=*.js --include=*.py --include=*.go . | grep -vi node_modules | head -50
   ```
   Note the files that come back — that's where Phase 3 will happen. **Do not edit them yet.**
5. Write down (in a scratch file or to the human): the run command, the build command,
   the runtime version, and the 2–3 files that look like the provider integration point.

**Exit criteria:** you can state, in one paragraph, how this project builds, how it runs,
and roughly where an LLM provider would be wired in.

---

## Phase 1 — Get the software running (NO Concentrate yet) 🚦

**This is the gate. Nothing about Concentrate happens until this phase passes.**

1. Install dependencies exactly as the repo prescribes (`pnpm install`, `npm ci`,
   `poetry install`, `uv sync`, `go mod download`, …). Respect any repo-specific
   setup helper (e.g. n8n has `pnpm agent:setup`).
2. Build. **Always redirect long build output to a log** and tail it — don't flood the
   terminal:
   ```bash
   <build cmd> > build.log 2>&1; tail -n 30 build.log
   ```
3. Start the app **unmodified**, with its stock/default LLM config (or none). Use the
   default provider or a placeholder — the point is to prove the app boots, serves its
   UI/API, and you can reach it.
4. **Remote-access checklist** (this bit the n8n integration — budget for it):
   - Bind to all interfaces, not just loopback (`0.0.0.0`), if you're hitting it from
     another machine.
   - Set whatever **public base URL / webhook URL** env var the app has to the VM's
     reachable address. Web apps that POST back to themselves (chat widgets, webhooks,
     OAuth callbacks) will silently 404 if this points at `localhost`. Symptoms like
     "failed to receive response" are usually *this*, not a code bug.
   - If the cloud security group blocks the port, use an SSH tunnel instead of opening
     it: `ssh -L <port>:localhost:<port> user@vm`.
   - Disable secure-cookie enforcement if serving plain HTTP over an IP during testing.

**Exit criteria:** the human can open the app in a browser (or hit its API) and it
works with a stock model/provider. **Stop here and confirm with the human before Phase 2.**

---

## Phase 2 — Baseline test (still no Concentrate)

**Goal:** prove the LLM path itself works end-to-end using a *known-good* provider
(e.g. stock OpenAI, or a local model) BEFORE introducing Concentrate. This isolates
"does the app work" from "is my Concentrate wiring correct."

1. Configure the app's existing OpenAI (or other) provider with a valid key.
2. Run the simplest possible LLM interaction the app supports (one chat turn / one
   completion / one agent step).
3. Confirm you get a real model response.

**Exit criteria:** a successful LLM round-trip through the app on a known provider.
Now you *know* any failure in Phase 3 is Concentrate-specific. **Confirm with the human.**

---

## Phase 3 — Add Concentrate

**Only start once Phases 1 & 2 pass.** Do the smallest thing that works first, then improve.

### 3a. Sanity-check the gateway from the VM (before touching code)
```bash
curl -s https://api.concentrate.ai/v1/models \
  -H "Authorization: Bearer $CONCENTRATE_API_KEY" | head -c 500
```
You should get a JSON model list. If this fails, it's networking/keys, not the app.

### 3b. Wire it in — pick the lowest-effort path that applies:
- **App accepts a custom OpenAI base URL** (most common): just set base URL to
  `https://api.concentrate.ai/v1`, the API key, and a model name. Often *zero code* —
  pure config/env. Try this first.
- **App has a provider registry/plugin system** (n8n's case): add Concentrate as a new
  provider/node/credential, cloning the nearest existing OpenAI-compatible provider
  (for n8n it was the DeepSeek node → a `ChatOpenAI` pointed at Concentrate's base URL,
  with a `useResponsesApi` toggle defaulting to `true`). Register it wherever providers
  are declared.
- **App hardcodes OpenAI**: add a config branch/env switch for base URL + key. Keep the
  change minimal and match surrounding code style.

### 3c. Prefer the Responses API, keep completions as fallback
If the app's LLM client library supports it, default to `/v1/responses` and expose a
toggle to fall back to `/v1/chat/completions`. If it only speaks chat/completions,
that's fine — ship that.

### 3d. Model list
Populate the model picker (or config default) from `GET /v1/models` if the app supports
dynamic lists; otherwise document a sensible default like `auto` or
`anthropic/claude-opus-4-8`.

### 3e. Rebuild & restart
Rebuild the changed package/app (redirect to log), restart, and repeat the Phase 2 test
— but now pointed at Concentrate.

**Exit criteria:** the same end-to-end interaction from Phase 2 now succeeds through
Concentrate, verified live by the human.

---

## Phase 4 — Verify, document, hand off

1. **Verify live**, not just via unit tests: credential/connection test passes, a real
   chat/agent turn returns a Concentrate response, streaming works if applicable.
2. Write a short `CONCENTRATE_WORK_SUMMARY.md` in the repo capturing:
   - what was built/changed (file list),
   - the exact run command + required env vars,
   - the API facts you relied on,
   - every gotcha that cost you time (future-you will thank you),
   - PR / branch state.
3. Open a **draft PR** against the project's fork if that's the workflow. Follow the
   repo's PR conventions. If it's an upstream OSS repo, keep the change idiomatic and
   self-contained so it's mergeable.

---

## Known gotchas (learned the hard way on n8n — check these first)

| Symptom | Real cause | Fix |
|---|---|---|
| Chat UI: "failed to receive response" / webhook 404 | App POSTs to `localhost` because public base/webhook URL env var wasn't set | Set the app's public URL env var to the VM's reachable address |
| Responses API rejected by an agent/orchestration layer | Some frameworks gate the Responses API behind a min version (n8n blocks it on AI Agent ≤ v2.2 due to an upstream LangChain tools bug) | Use the newer component version, or fall back to chat/completions |
| First build fails immediately | Runtime version mismatch | Use the repo's pinned Node/Python/Go version (nvm/asdf/etc.) |
| Can't reach the port from your laptop | Cloud security group blocks it | SSH tunnel: `ssh -L port:localhost:port user@vm` |
| Login/session breaks over HTTP-by-IP | Secure-cookie enforcement | Disable secure cookies for the HTTP test instance |
| Stale build after switching branches | Cached/partial build outputs | Use the repo's clean/reset script before rebuilding |

---

## Security hygiene

- **Never hardcode or commit the Concentrate API key.** Use env vars or the app's
  encrypted credential store. Scrub keys/PATs from git config, logs, and shell history.
- If you used a GitHub PAT to push, **rotate it** after — treat any key shared in
  plaintext as compromised.
- Don't paste keys into public PRs, issues, or test fixtures.

---

## Reference: the n8n integration (worked example)

- **Repo:** `concentrate-ai/n8n` fork, TypeScript monorepo (pnpm + turbo).
- **What was added:** a **Concentrate Chat Model** sub-node + **Concentrate** credential
  in `packages/@n8n/nodes-langchain/`, cloned from the DeepSeek gateway node. Built a
  LangChain `ChatOpenAI` pointed at `https://api.concentrate.ai/v1` with
  `useResponsesApi: true` by default (toggle for chat/completions fallback).
- **Registered** the node + credential in that package's `package.json`.
- **Ran from source** (Node 22 via nvm, pnpm 10.32.1), rebuilt the one package after
  changes rather than the whole monorepo (`cd packages/@n8n/nodes-langchain && pnpm build`).
- **Verified live** in the GUI: connection test green, Responses API streaming through
  Chat Trigger → AI Agent (v3+) → Concentrate + Simple Memory.
- Full detail: `/home/adidev/concentrate-n8n/CONCENTRATE_WORK_SUMMARY.md`.

Use it as a template for *shape*, not as a recipe to copy blindly — every OSS project
wires providers differently. Phases 0–2 tell you where; Phase 3 is where the project's
specifics take over.

# Claude Gateway — subscription-powered local API (Ubuntu)

This version **uses your existing Claude Code subscription login by default**. You do **not** need to buy an Anthropic Console API key just to run the local gateway. The gateway creates a separate local `lcg_...` key that your app uses to authenticate to **your own server**. It is **not** an official Anthropic API key.

As of Anthropic's 7 October 2026 update, Claude Code `claude -p` and third-party integrations may use subscription limits. Usage counts against your Claude plan's existing usage allowances. Consult the current [Anthropic documentation](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) and your plan settings for changes and extra-usage billing options.

The server includes a browser dashboard, hashed local keys, per-key requests/minute and rolling 30-day request quotas, logs (metadata only), and saved chat sessions. The API supports **non-streaming plain-text conversation** and is **partially** compatible with OpenAI `/v1/chat/completions` and Anthropic `/v1/messages`.

## 1. Prerequisites: sign in to Claude Code on the SAME Ubuntu account

```bash
claude --version
claude auth login
claude auth status
claude -p 'Say hello in one sentence' --output-format json
```

Log in with **your Claude subscription**, **not** the `--console` option. If you're already signed in, you don't need to log in again. This gateway checks that `claude auth status` reports `authMethod: "claude.ai"`. If you've used Console billing, re-authenticate with your subscription. Your browser/CLI login stays managed by Claude Code; this gateway never reads or copies OAuth tokens.

**Avoid inadvertent API billing:** Claude Code prioritizes `ANTHROPIC_API_KEY` over subscription when set. The gateway removes API/cloud credential overrides from its Claude subprocess environment. The optional **direct API backend** is only used if you explicitly select `GATEWAY_BACKEND=api`.

## 2. Install and run

```bash
unzip claude_gateway_subscription.zip
cd claude_gateway_subscription
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py doctor
python app.py setup
python app.py serve
```

Save the `lcga_...` **admin token** printed during `setup` (it cannot be recovered). `setup` resets only the admin token when run a second time; it does not delete your app keys. Start `serve` with the **same Ubuntu user** that logged in to Claude Code, not with `sudo` and not in a Docker container lacking your Claude Code login.

Open **http://127.0.0.1:8765** in your browser. Enter the `lcga_...` token, click **Create key**, and copy the new `lcg_...` app key. You can create or revoke independent keys for each application. No Anthropic API key is required in this default mode.

You can make CLI mode explicit (optional):

```bash
export GATEWAY_BACKEND=cli
python app.py serve
```

If `claude` isn't on the `PATH` of the process running the server, export an absolute executable path, e.g. `export CLAUDE_BIN="$HOME/.local/bin/claude"`.

## 3. Connect the app

| Client | Base URL | API key | Model |
| --- | --- | --- | --- |
| OpenAI-style SDK | `http://127.0.0.1:8765/v1` | Generated `lcg_...` | `sonnet` |
| Anthropic SDK | `http://127.0.0.1:8765` | Generated `lcg_...` | `sonnet` |

Supported aliases: `sonnet`, `opus`, `haiku` (the CLI resolves availability based on your account). Your app sends `Authorization: Bearer lcg_...` (OpenAI style) or `x-api-key: lcg_...` (Anthropic style). The generated `lcg_` key belongs to **your gateway only**.

**Smoke test** (after creating an `lcg_...` key):

```bash
export LOCAL_CLAUDE_GATEWAY_KEY='lcg_PASTE_KEY_FROM_DASHBOARD'
curl --fail-with-body http://127.0.0.1:8765/v1/chat/completions \
  -H "Authorization: Bearer $LOCAL_CLAUDE_GATEWAY_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"sonnet","messages":[{"role":"user","content":"Say hello in Hebrew"}],"stream":false}'
```

**Node.js example** (your app's **backend**, not browser frontend):

```ts
import OpenAI from 'openai';
const ai = new OpenAI({
  apiKey: process.env.LOCAL_CLAUDE_GATEWAY_KEY!,
  baseURL: process.env.LOCAL_CLAUDE_GATEWAY_URL ?? 'http://127.0.0.1:8765/v1',
});
const completion = await ai.chat.completions.create({
  model: 'sonnet',
  messages: [{role: 'user', content: 'Hello!'}],
  stream: false,
});
console.log(completion.choices[0].message.content);
```

See **`PROMPT_FOR_CLAUDE.md`** for the full integration instruction to paste into Claude Code working on your app.

## 4. Optional direct API backend (requires official key / possible charges)

Only if you deliberately want to use the official API, launch **a separate process** with:

```bash
export GATEWAY_BACKEND=api
export ANTHROPIC_API_KEY='sk-ant-YOUR_OFFICIAL_KEY'
python app.py serve
```

In this mode, API usage can incur separate charges and no longer uses your subscription allocation. The dashboard clearly reports whether the current backend is `cli` or `api`. To use the subscription again, `unset GATEWAY_BACKEND ANTHROPIC_API_KEY` and restart the server. You may need to set `GATEWAY_API_SONNET_MODEL`, `GATEWAY_API_OPUS_MODEL`, `GATEWAY_API_HAIKU_MODEL` if model IDs change.

## 5. Security and current limits

- **Private by default:** binds to `127.0.0.1`, not `0.0.0.0`. Never expose port 8765 directly to the public internet. For Docker/another machine, use an authenticated private encrypted tunnel / server-side proxy; `localhost` in another container/machine is not the Ubuntu host.
- Keep the `lcg_...` key in your app's **backend environment variables**; never in React/client-side JS, a public repository, mobile app, or logs.
- The gateway checks `claude auth status` and accepts **only** a `claude.ai` subscription login when using CLI mode. It strips inherited Anthropic API key and cloud provider environment variables when spawning Claude.
- `claude -p --bare --tools '' --disallowedTools mcp__*` disables coding tools, filesystem access, shell execution, and MCP tool calls. It is a **text-chat gateway, not a remote coding-agent execution gateway**.
- **Not supported:** streaming/SSE, tool calls, images, audio, JSON schema responses, embeddings, or full OpenAI/Anthropic API compatibility. `max_tokens` is accepted in the API but not strictly enforced by the CLI bridge. No cross-request CLI context is kept unless you use the gateway's own saved sessions API.
- Input limit: 100,000 characters, up to 40 messages per request; each CLI invocation has a 180-second timeout. Local key quotas count requests (not tokens) and do not change Claude plan usage limits.
- The local SQLite database in `.data/` stores SHA-256 hashes of random `lcg_` keys and logs request metadata; **saved sessions** additionally store their full messages locally for seven days (or until deleted). `setup` prints an admin token one time.
- `GATEWAY_CORS_ORIGINS` can enable explicit browser origins for development, but **CORS does not protect API keys**; prefer a trusted app backend.
- If the CLI login has usage limits, an actual model refusal, or a CLI version incompatibility, you may get `502` or `503`. Check `python app.py doctor` and `claude -p 'hello'`. Passing local tests is not proof of a live Claude connection.

## 6. Upgrading an earlier installation

The new ZIP uses a separate `claude_gateway_subscription/` directory. Do not accidentally run the old `claude_gateway_advanced` server on the same port.

If you want to keep keys and logs from your old installation and **you trust that local data**, stop both servers first and copy the `.data/` directory from your old project into this new folder (preserving file owner and permissions). Otherwise run the fresh `setup` workflow above. The same schema is used.

## Dashboard login JavaScript fix (13 Oct 2026)

This package fixes a missing closing brace in the dashboard's **Unlock dashboard** JavaScript handler. Older packages show an inert button with no error. The fix is **front-end only**; it does not alter the API gateway database, saved keys, credentials, or subscription backend.

**If you already installed this gateway:** The simplest fix is to replace only `templates/index.html` with the one from this ZIP, then hard-refresh the page (Ctrl+Shift+R). You do not need to run `python app.py setup` again. Keep the existing `.data/` directory unchanged.

## 7. Tests (mocked Claude Code; no live usage)

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Files: `app.py` gateway, `templates/index.html` control center, `tests/test_app.py` tests, `PROMPT_FOR_CLAUDE.md` app integration prompt.

# Task for Claude Code: connect my app to my subscription-powered local gateway

I have a **Claude Gateway** running on my Ubuntu machine. It connects to my **existing Claude Code subscription login** through the official `claude -p` CLI and provides **its own locally-generated API keys**. It does **not** require me to purchase an Anthropic Console API key for the gateway's default CLI mode.

Please implement this integration in my **existing application**, preserving its architecture and existing behavior.

1. Inspect the project first. Find its existing AI provider integration (OpenAI SDK, Anthropic SDK, direct fetch, server or browser app). Add a configurable provider named `local-claude-gateway`.
2. Use these **backend-only environment variables** (create `.env.example` with placeholders; ignore `.env` in git):
   - `LOCAL_CLAUDE_GATEWAY_KEY` = my `lcg_...` local key from the gateway dashboard.
   - `LOCAL_CLAUDE_GATEWAY_URL` = `http://127.0.0.1:8765/v1` for OpenAI-compatible SDK, or `http://127.0.0.1:8765` for Anthropic SDK (the latter appends `/v1/messages`).
   - `LOCAL_CLAUDE_GATEWAY_MODEL` = `sonnet` by default; also allow `opus` and `haiku`.
3. All AI requests for this provider must go through my own **app backend**, then the local gateway. Never call the gateway directly from client-side JavaScript or bundle the secret into mobile/browser code. Auth: `Authorization: Bearer lcg_...` (OpenAI-compatible) or `x-api-key: lcg_...` (Anthropic-compatible).
4. Support **plain-text, non-streaming** conversations (`stream: false`) with the existing chat history. The gateway does **not** support SSE streaming, tools/function calling, attachments/images, structured output, or full SDK surface compatibility. If the existing app needs these, flag the incompatibility and don't silently break it.
5. Add a provider/model/baseURL configuration control where appropriate, but **never reveal the key to the frontend**. Add a safe health check routed through the app backend.
6. Handle common failures cleanly: gateway unavailable, wrong local key (401), key throttled (429), Claude Code not signed in with a subscription (503), CLI failure/usage limit (502), and timeouts. Never log prompts, secrets or Claude's authentication details.
7. The gateway runs by default on localhost on **my Ubuntu computer**. Check Docker/WSL/remoteness before assuming the app sees the Ubuntu host as `127.0.0.1`. Don't expose the gateway or port 8765 directly to the internet.
8. Verify setup on my machine: `claude auth status`, `python app.py doctor`, and one small end-to-end message through the gateway if it is running. If unavailable, implement and test the integration with mocks rather than claiming live verification.
9. Important: **do not ask me to create `ANTHROPIC_API_KEY` for the default gateway mode**, do not use `claude setup-token` or extract/copy the CLI's OAuth tokens. The gateway launches `claude -p` with normal subscription authentication already established on the Ubuntu host. Its `lcg_...` key is only used to authenticate apps to the gateway.
10. After implementing, report changed files, run tests, and explain the exact local run commands and environment variables needed. Preserve all existing features.

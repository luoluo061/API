# Web LLM Adapter

`web-llm-adapter` is a Playwright-based adapter service that turns web-only LLM workflows into a callable internal capability.

It is not:
- a crawler
- a generic browser automation bot
- an official model API integration

It is:
- a browser-driven model invocation adapter
- a unified `/chat` HTTP interface for upper-layer agents or workflows
- a provider abstraction that hides page selectors, login state, retries, and diagnostics

## Default v1 mode

The default and verified first-version path is `CDP` mode.

What this means:
- you manually start a logged-in Edge instance with remote debugging enabled
- the service attaches to that running browser through `connect_over_cdp`
- `/profiles/verify` checks login state and page readiness in that live browser
- `/chat` sends a real prompt and extracts the real answer from the page

`launch` mode and persistent profile cloning are still available as experimental fallback paths, but they are no longer the primary documented workflow.

## Minimal runbook

### 1. Start a logged-in Edge with CDP enabled

Use a dedicated user-data-dir and keep this Edge window open:

```powershell
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --remote-debugging-port=9222 --user-data-dir="E:\API\.profiles\masters\doubao-edge" "https://www.doubao.com/chat/"
```

In that window:
- sign in to Doubao
- confirm you can manually send a message and receive a reply
- leave the browser open

### 2. Confirm port `9222` is reachable

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

Expected result:
- returns JSON
- includes `webSocketDebuggerUrl`

If this fails, the service will later return `cdp_unreachable`.

### 3. Start the service

```powershell
cd E:\API
py -m pip install -e .
$env:WEB_LLM_BROWSER_MODE = "cdp"
$env:WEB_LLM_CDP_URL = "http://127.0.0.1:9222"
$env:WEB_LLM_MASTER_PROFILE_DIR = "E:\API\.profiles\masters\doubao-edge"
$env:WEB_LLM_TRACE_MODE = "failure"
$env:WEB_LLM_MOCK_MODE = "0"
py -m uvicorn web_adapter.main:app --host 127.0.0.1 --port 8000
```

`WEB_LLM_BROWSER_MODE` now defaults to `cdp`, so setting it explicitly is optional.

### 4. Check `/health`

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

`/health` is a system-level precheck. In CDP mode it means:
- `browser`: whether `127.0.0.1:9222` is reachable and has browser contexts
- `master_profile`: which dedicated Edge profile directory this project expects you to use
- `runtime_profile_root`: present for compatibility; unused in default CDP mode
- `provider`: reminder that real provider verification still belongs to `/profiles/verify`

A healthy CDP response should look conceptually like:
- `browser.status = ok`
- `browser.detail = cdp ready: http://127.0.0.1:9222`
- `provider.detail = cdp reachable; use /profiles/verify for login and page readiness`

### 5. Check `/profiles/verify`

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/profiles/verify" -ContentType "application/json" -Body '{"provider":"doubao"}'
```

`/profiles/verify` is the browser-backed validation step. In CDP mode it means:
- attach to the live Edge instance
- open a service-owned page in that browser
- navigate to Doubao
- verify that login is still valid
- verify that the chat page is ready for interaction

Expected success:
- `status = ok`
- `login_state = logged_in`
- `artifacts.page_url` points at the Doubao chat page

Expected failure patterns:
- `cdp_unreachable`: CDP endpoint not reachable or has no contexts
- `login_required`: browser opened, but Doubao session is not logged in
- `page_not_ready`: page loaded but input area is not ready for interaction

### 6. Run a real `/chat`

Use an ASCII prompt first when validating end-to-end to avoid local shell encoding noise:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/chat" -ContentType "application/json" -Body '{"provider":"doubao","prompt":"Reply with exactly OK."}'
```

Expected success:
- `status = ok`
- `content = OK`
- `artifacts.page_url` points at a real Doubao conversation URL

Expected failure patterns:
- `login_required`: the browser lost Doubao login state
- `provider_timeout`: the prompt was sent but no stable assistant text was detected before timeout
- `extract_empty`: a reply container appeared but extracted text was empty
- `page_not_ready`: the page loaded but the input area was not usable

## Diagnostics

Every request writes artifacts under `.artifacts/<timestamp>-<request_id>/`.

Look at these first:
- `request.log`: execution timeline and structured error detail
- `failure.png`: what the page looked like at failure time
- `page.html`: DOM snapshot for selector and extraction debugging
- `trace.zip`: Playwright trace when tracing is enabled and captured

Successful real CDP validation on this machine produced:
- extracted content `OK`
- a real Doubao conversation URL
- request log at `E:\API\.artifacts\20260312T063610Z-b77a22f1860c44f59b9ea5e13cfcdcdf\request.log`

## Error codes

The main first-version operational errors are:
- `cdp_unreachable`: service cannot attach to `WEB_LLM_CDP_URL`
- `login_required`: Doubao redirected to login or showed login indicators
- `provider_timeout`: no stable assistant response detected before timeout
- `extract_empty`: response flow completed but extracted text was empty
- `page_not_ready`: page opened but input controls were not ready

Other retained errors:
- `master_profile_missing`
- `profile_locked`
- `runtime_profile_copy_failed`
- `browser_unavailable`
- `page_navigation_failed`
- `send_failed`

## Environment variables

Primary CDP settings:
- `WEB_LLM_BROWSER_MODE`: `cdp` or `launch`, default `cdp`
- `WEB_LLM_CDP_URL`: default `http://127.0.0.1:9222`
- `WEB_LLM_MASTER_PROFILE_DIR`: dedicated Edge user-data-dir used in the manual CDP workflow
- `WEB_LLM_TRACE_MODE`: `off`, `failure`, or `always`
- `WEB_LLM_MOCK_MODE`: `1` to bypass browser calls
- `WEB_LLM_REQUEST_TIMEOUT_SECONDS`: request timeout
- `WEB_LLM_QUEUE_WAIT_SECONDS`: queue acquisition timeout
- `WEB_LLM_ARTIFACT_DIR`: diagnostics output directory

Experimental launch/profile settings:
- `WEB_LLM_HEADLESS`: `1` or `0`, only used in `launch` mode
- `WEB_LLM_PROFILE_MODE`: `dedicated` or `clone`, only used in `launch` mode
- `WEB_LLM_RUNTIME_PROFILE_ROOT`: root directory for runtime profile copies
- `WEB_LLM_RUNTIME_PROFILE_RETENTION`: `success_delete_failure_keep`, `delete_all`, or `keep_all`
- `WEB_LLM_BROWSER_CHANNEL`: Chromium channel for `launch` mode, default `msedge`

## Current scope

Initial implementation includes:
- FastAPI service with `POST /chat`, `POST /profiles/verify`, and `GET /health`
- single-worker serialized execution
- CDP-first browser attachment
- Doubao web provider contract
- structured diagnostics with logs, screenshots, HTML snapshots, and optional traces
- retained experimental `launch` and profile-copy paths for follow-up experiments
- mock mode for validating the API flow without a real browser

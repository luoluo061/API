from __future__ import annotations

import asyncio
import re
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any

from web_adapter.config import Settings
from web_adapter.errors import AdapterError
from web_adapter.logging_utils import append_request_log
from web_adapter.providers.base import ProviderContext, ProviderResult


STRUCTURED_RESPONSE_SCRIPT = r'''
(node) => {
  const references = [];
  const seenReferences = new Set();

  const normalizeText = (value) => (value || '')
    .replace(/\u00a0/g, ' ')
    .replace(/\r/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  const isHidden = (el) => {
    if (!(el instanceof HTMLElement)) {
      return false;
    }
    const style = window.getComputedStyle(el);
    return style.display === 'none' || style.visibility === 'hidden';
  };

  const isIgnored = (el) => {
    if (!(el instanceof HTMLElement)) {
      return false;
    }
    return Boolean(
      el.closest(
        '[data-testid="message_action_bar"], [data-testid="suggest_message_list"], [data-testid="search-reference-ui-v3"]'
      )
    );
  };

  const addReference = (title, url) => {
    const normalizedUrl = (url || '').trim();
    if (!normalizedUrl || seenReferences.has(normalizedUrl)) {
      return;
    }
    seenReferences.add(normalizedUrl);
    references.push({ title: (title || normalizedUrl).trim(), url: normalizedUrl });
  };

  const collectReferences = (root) => {
    Array.from(root.querySelectorAll('a')).forEach((link) => {
      if (isIgnored(link) || isHidden(link)) {
        return;
      }
      const title = normalizeText(link.innerText || link.textContent || '');
      addReference(title, link.href || '');
    });
  };

  const serializeInline = (current) => {
    if (!current) {
      return '';
    }
    if (current.nodeType === Node.TEXT_NODE) {
      return current.textContent || '';
    }
    if (current.nodeType !== Node.ELEMENT_NODE) {
      return '';
    }

    const el = current;
    if (isHidden(el) || isIgnored(el)) {
      return '';
    }

    const tag = el.tagName.toLowerCase();
    if (tag === 'br') {
      return '\n';
    }
    if (tag === 'a') {
      const text = normalizeText(Array.from(el.childNodes).map(serializeInline).join('')) || normalizeText(el.innerText || '');
      const url = el.href || '';
      addReference(text, url);
      if (text && url && text !== url) {
        return `[${text}](${url})`;
      }
      return text || url;
    }
    if (tag === 'strong' || tag === 'b') {
      const text = normalizeText(Array.from(el.childNodes).map(serializeInline).join(''));
      return text ? `**${text}**` : '';
    }
    if (tag === 'em' || tag === 'i') {
      const text = normalizeText(Array.from(el.childNodes).map(serializeInline).join(''));
      return text ? `*${text}*` : '';
    }
    if (tag === 'code' && !el.closest('pre')) {
      const text = normalizeText(el.innerText || el.textContent || '');
      return text ? `\`${text}\`` : '';
    }

    return Array.from(el.childNodes).map(serializeInline).join('');
  };

  const extractCodeBlock = (el) => {
    const pre = el.tagName.toLowerCase() === 'pre' ? el : el.querySelector(':scope > pre, pre');
    if (!pre || isIgnored(pre) || isHidden(pre)) {
      return null;
    }
    const codeEl = pre.querySelector('code');
    const sourceClasses = [el.className || '', pre.className || '', codeEl?.className || ''].join(' ');
    const match = sourceClasses.match(/language-([A-Za-z0-9_+-]+)/);
    const code = ((codeEl || pre).innerText || '').replace(/\r/g, '').replace(/\n$/, '');
    if (!normalizeText(code)) {
      return null;
    }
    return {
      type: 'code_block',
      language: match ? match[1] : '',
      code,
    };
  };

  const extractList = (el) => {
    const ordered = el.tagName.toLowerCase() === 'ol';
    const items = Array.from(el.children)
      .filter((child) => child.tagName && child.tagName.toLowerCase() === 'li' && !isHidden(child) && !isIgnored(child))
      .map((li) => normalizeText(li.innerText || li.textContent || ''))
      .filter(Boolean);
    if (!items.length) {
      return null;
    }
    return { type: 'list', ordered, items };
  };

  const extractTextBlock = (el, type = 'paragraph') => {
    const text = normalizeText(Array.from(el.childNodes).map(serializeInline).join('')) || normalizeText(el.innerText || '');
    if (!text) {
      return null;
    }
    return { type, text };
  };

  const containsDirectBlockChildren = (el) => {
    return Array.from(el.children).some((child) => {
      if (isHidden(child) || isIgnored(child)) {
        return false;
      }
      const childTag = child.tagName.toLowerCase();
      return ['div', 'section', 'article', 'p', 'ul', 'ol', 'blockquote', 'pre', 'h1', 'h2', 'h3'].includes(childTag)
        || child.querySelector('pre')
        || String(child.className || '').includes('code-block');
    });
  };

  const blocks = [];

  const pushBlock = (block) => {
    if (!block) {
      return;
    }
    if (block.type === 'paragraph' || block.type === 'blockquote' || block.type === 'heading') {
      if (!normalizeText(block.text)) {
        return;
      }
    }
    if (block.type === 'list' && (!Array.isArray(block.items) || !block.items.length)) {
      return;
    }
    if (block.type === 'code_block' && !normalizeText(block.code)) {
      return;
    }
    blocks.push(block);
  };

  const walk = (current) => {
    if (!current) {
      return;
    }
    if (current.nodeType === Node.TEXT_NODE) {
      const text = normalizeText(current.textContent || '');
      if (text) {
        pushBlock({ type: 'paragraph', text });
      }
      return;
    }
    if (current.nodeType !== Node.ELEMENT_NODE) {
      return;
    }

    const el = current;
    if (isHidden(el) || isIgnored(el)) {
      return;
    }

    const tag = el.tagName.toLowerCase();

    if (tag === 'pre') {
      pushBlock(extractCodeBlock(el));
      return;
    }

    if (tag === 'h1' || tag === 'h2' || tag === 'h3') {
      const heading = extractTextBlock(el, 'heading');
      if (heading) {
        heading.level = Number(tag.slice(1));
        pushBlock(heading);
      }
      return;
    }

    if (tag === 'blockquote') {
      pushBlock(extractTextBlock(el, 'blockquote'));
      return;
    }

    if (tag === 'ul' || tag === 'ol') {
      pushBlock(extractList(el));
      return;
    }

    if (tag === 'p') {
      pushBlock(extractTextBlock(el));
      return;
    }

    if (tag === 'div' || tag === 'section' || tag === 'article') {
      const directPre = Array.from(el.children).find((child) => child.tagName && child.tagName.toLowerCase() === 'pre');
      if (directPre && el.children.length === 1) {
        pushBlock(extractCodeBlock(directPre));
        return;
      }
      if (containsDirectBlockChildren(el)) {
        Array.from(el.childNodes).forEach(walk);
        return;
      }
      pushBlock(extractTextBlock(el));
      return;
    }

    if (tag === 'span') {
      const text = normalizeText(Array.from(el.childNodes).map(serializeInline).join('')) || normalizeText(el.innerText || '');
      if (text) {
        pushBlock({ type: 'paragraph', text });
      }
      return;
    }

    Array.from(el.childNodes).forEach(walk);
  };

  collectReferences(node);
  Array.from(node.childNodes).forEach(walk);

  const mergedBlocks = [];
  for (const block of blocks) {
    const prev = mergedBlocks[mergedBlocks.length - 1];
    if (prev && prev.type === 'paragraph' && block.type === 'paragraph') {
      prev.text = normalizeText(`${prev.text}\n${block.text}`);
      continue;
    }
    mergedBlocks.push(block);
  }

  return {
    blocks: mergedBlocks,
    references,
    plain_text: normalizeText(node.innerText || ''),
  };
}
'''


class DoubaoProvider:
    name = "doubao"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def prepare(self, context: ProviderContext) -> None:
        if self._settings.mock_mode:
            return

        page = context.browser.page
        assert page is not None
        try:
            await page.goto(self._settings.base_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
        except Exception as exc:
            raise AdapterError("page_navigation_failed", detail=str(exc), provider=self.name) from exc

        await self._raise_for_login_barrier(page)
        await self._ensure_page_ready(page)

    async def send_prompt(self, context: ProviderContext, prompt: str) -> None:
        if self._settings.mock_mode:
            return

        page = context.browser.page
        assert page is not None
        input_box = page.locator(self._settings.doubao_input_selector).first

        try:
            context.metadata["_baseline_receive_texts"] = await self._extract_receive_texts(page)
            context.metadata["_baseline_receive_count"] = await page.locator('[data-testid="receive_message"]').count()
            context.metadata["_prompt"] = prompt
            await input_box.wait_for(timeout=5000)
        except Exception as exc:
            raise AdapterError("page_not_ready", detail=f"input selector unavailable: {exc}", provider=self.name) from exc

        try:
            tag_name = await input_box.evaluate("(node) => node.tagName.toLowerCase()")
            if tag_name == "textarea":
                await input_box.fill(prompt)
            else:
                await input_box.click()
                await input_box.fill("")
                await input_box.type(prompt)
        except Exception as exc:
            raise AdapterError("send_failed", detail=f"input failed: {exc}", provider=self.name) from exc

        try:
            send_button = await self._resolve_send_button(page)
            await send_button.click(timeout=5000)
            await page.wait_for_timeout(1500)
        except Exception as exc:
            raise AdapterError("send_failed", detail=f"send button failed: {exc}", provider=self.name) from exc

        await self._raise_for_login_barrier(page)

    async def wait_response(self, context: ProviderContext) -> None:
        if self._settings.mock_mode:
            await asyncio.sleep(0)
            return

        page = context.browser.page
        assert page is not None
        baseline_texts = list(context.metadata.get("_baseline_receive_texts", []))
        baseline_receive_count = int(context.metadata.get("_baseline_receive_count", 0))
        deadline = asyncio.get_event_loop().time() + context.timeout_seconds
        stable_text = ""
        stable_hits = 0

        while asyncio.get_event_loop().time() < deadline:
            await self._raise_for_login_barrier(page)

            receive_messages = page.locator('[data-testid="receive_message"]')
            receive_count = await receive_messages.count()
            current_texts = await self._extract_receive_texts(page)
            candidate = self._select_candidate_text(current_texts, baseline_texts)
            latest_receive = receive_messages.nth(receive_count - 1) if receive_count else None
            controls = await self._inspect_response_controls(page, latest_receive)

            if candidate:
                if candidate == stable_text:
                    stable_hits += 1
                else:
                    stable_text = candidate
                    stable_hits = 1

                controls["stable_text_hits"] = stable_hits
                controls["text_length"] = len(candidate)
                context.metadata["_completion_signals"] = controls
                context.metadata["_response_text"] = candidate

                if await self._is_response_complete(page, latest_receive, stable_hits, controls):
                    append_request_log(
                        context.artifacts.request_log_path,
                        "response_controls_detected",
                        request_id=context.request_id,
                        provider=self.name,
                        **controls,
                    )
                    return

            if receive_count > baseline_receive_count and current_texts and stable_hits >= 4:
                latest_text = current_texts[-1]
                if latest_text:
                    context.metadata["_response_text"] = latest_text
                    return

            await page.wait_for_timeout(1200)

        raise AdapterError("provider_timeout", detail="no stable assistant text detected", provider=self.name)
    async def extract_result(self, context: ProviderContext) -> ProviderResult:
        if self._settings.mock_mode:
            content = f"[mock:doubao] {context.metadata.get('echo_prompt', False) and 'echo enabled' or 'response ready'}"
            return ProviderResult(
                content=content,
                usage_like_meta={"mode": "mock"},
                page_url=self._settings.base_url,
            )

        page = context.browser.page
        assert page is not None
        await self._raise_for_login_barrier(page)

        hinted = str(context.metadata.get("_response_text", "")).strip()
        settled_text = await self._wait_for_settled_response_text(page, hinted)
        latest_receive = await self._get_latest_receive_message(page)
        completion_signals = context.metadata.get("_completion_signals", {})

        structured = await self._extract_structured_response(page)
        blocks = self._clean_serialized_blocks(structured.get("blocks", []))
        content = self._clean_markdown_tail(self._render_blocks_to_markdown(blocks))
        extraction_path = "structured"
        content_format = "markdown"

        if not self._is_structured_result_trustworthy(content, blocks, settled_text):
            append_request_log(
                context.artifacts.request_log_path,
                "structured_result_short",
                request_id=context.request_id,
                provider=self.name,
                structured_length=len(content),
                settled_length=len(settled_text),
            )
            await page.wait_for_timeout(1200)
            structured = await self._extract_structured_response(page)
            blocks = self._clean_serialized_blocks(structured.get("blocks", []))
            content = self._clean_markdown_tail(self._render_blocks_to_markdown(blocks))

        if not self._is_structured_result_trustworthy(content, blocks, settled_text):
            append_request_log(
                context.artifacts.request_log_path,
                "copy_fallback_started",
                request_id=context.request_id,
                provider=self.name,
            )
            copied = await self._extract_via_copy(page, latest_receive)
            copied = self._clean_copy_text(copied)
            if self._is_copy_result_trustworthy(copied, settled_text):
                content = copied
                extraction_path = "copy_fallback"
                content_format = "text"
                blocks = []
                append_request_log(
                    context.artifacts.request_log_path,
                    "copy_fallback_succeeded",
                    request_id=context.request_id,
                    provider=self.name,
                    copied_length=len(copied),
                    reason="structured_tail_detected" if self._has_interactive_tail(content) else "structured_too_short",
                )
            else:
                append_request_log(
                    context.artifacts.request_log_path,
                    "copy_fallback_failed",
                    request_id=context.request_id,
                    provider=self.name,
                    copied_length=len(copied),
                )

        if not content and settled_text:
            content = settled_text
            extraction_path = "settled_text_fallback"
            content_format = "text"
            blocks = []
            append_request_log(
                context.artifacts.request_log_path,
                "settled_text_fallback_used",
                request_id=context.request_id,
                provider=self.name,
                settled_length=len(settled_text),
            )
        if not content:
            content = self._sanitize_response_text(await self._extract_latest_response_text(page))
            if content:
                extraction_path = "plain_text_fallback"
                content_format = "text"
                blocks = []
                append_request_log(
                    context.artifacts.request_log_path,
                    "plain_text_fallback_used",
                    request_id=context.request_id,
                    provider=self.name,
                    plain_text_length=len(content),
                )
        if not content:
            raise AdapterError("extract_empty", provider=self.name)

        references = self._merge_references(
            structured.get("references", []),
            await self._extract_latest_references(page),
        )
        usage_like_meta: dict[str, Any] = {
            "mode": "web",
            "response_length": len(content),
            "content_format": content_format,
            "blocks": blocks,
            "extraction_path": extraction_path,
            "completion_signals": completion_signals,
        }
        if references:
            usage_like_meta["references"] = references

        return ProviderResult(
            content=content,
            usage_like_meta=usage_like_meta,
            page_url=page.url,
        )
    async def recover(self, context: ProviderContext, failure: Exception) -> None:
        if self._settings.mock_mode:
            return

        page = context.browser.page
        if page is None:
            return
        try:
            await page.screenshot(path=str(context.artifacts.screenshot_path), full_page=True)
            html = await page.content()
            Path(context.artifacts.html_snapshot_path).write_text(html, encoding="utf-8")
        except Exception:
            return

    async def healthcheck(self, browser) -> tuple[str, str]:
        if self._settings.mock_mode:
            return "ok", "mock provider ready"
        page = browser.page
        if page is None:
            return "warn", "provider page not initialized"
        try:
            await page.goto(self._settings.base_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            await self._raise_for_login_barrier(page)
            await self._ensure_page_ready(page)
        except AdapterError as exc:
            if exc.error_key == "login_required":
                return "warn", exc.detail or exc.definition.message
            return "error", exc.detail or exc.definition.message
        except Exception as exc:
            return "error", str(exc)
        return "ok", page.url or self._settings.base_url

    async def _resolve_send_button(self, page):
        configured = page.locator(self._settings.doubao_send_selector)
        if await configured.count():
            return configured.last

        buttons = page.locator("button")
        count = await buttons.count()
        ignored_labels = {"\\u767b\\u5f55", "\\u4e0b\\u8f7d\\u7535\\u8111\\u7248"}
        for index in range(count - 1, -1, -1):
            candidate = buttons.nth(index)
            if await candidate.is_disabled():
                continue
            text = (await candidate.inner_text()).strip()
            if text in ignored_labels:
                continue
            classes = (await candidate.get_attribute("class")) or ""
            if "bg-dbx-fill-highlight" in classes or "rounded-full" in classes:
                return candidate

        raise AdapterError("selector_not_found", detail="send button unavailable", provider=self.name)

    async def _raise_for_login_barrier(self, page) -> None:
        if "from_logout=1" in page.url or "login" in page.url:
            raise AdapterError("login_required", detail=f"redirected to {page.url}", provider=self.name)
        for indicator in self._settings.doubao_login_indicators:
            locator = page.locator(indicator)
            try:
                if await locator.count() and await locator.first.is_visible():
                    raise AdapterError("login_required", detail=f"matched login indicator: {indicator}", provider=self.name)
            except AdapterError:
                raise
            except Exception:
                continue

    async def _ensure_page_ready(self, page) -> None:
        input_box = page.locator(self._settings.doubao_input_selector).first
        try:
            await input_box.wait_for(timeout=5000)
        except Exception as exc:
            raise AdapterError("page_not_ready", detail=f"input not ready: {exc}", provider=self.name) from exc

        try:
            count = await input_box.count()
            if count == 0:
                raise AdapterError("page_not_ready", detail="input selector count is zero", provider=self.name)
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError("page_not_ready", detail=f"input readiness check failed: {exc}", provider=self.name) from exc

    async def _extract_receive_texts(self, page) -> list[str]:
        texts = await page.locator('[data-testid="receive_message"] [data-testid="message_text_content"]').evaluate_all(
            """
            (nodes) => nodes
              .map((node) => (node.innerText || '').trim())
              .filter(Boolean)
            """
        )
        return [self._sanitize_response_text(text) for text in texts if self._sanitize_response_text(text)]

    async def _extract_structured_response(self, page) -> dict[str, Any]:
        locator = page.locator('[data-testid="receive_message"] [data-testid="message_text_content"]').last
        if not await locator.count():
            return {"blocks": [], "references": [], "plain_text": ""}
        try:
            data = await locator.evaluate(STRUCTURED_RESPONSE_SCRIPT)
        except Exception:
            return {"blocks": [], "references": [], "plain_text": ""}
        return data or {"blocks": [], "references": [], "plain_text": ""}

    async def _extract_latest_response_text(self, page) -> str:
        texts = await self._extract_receive_texts(page)
        return texts[-1] if texts else ""

    async def _extract_latest_references(self, page) -> list[dict[str, str]]:
        data = await page.locator('[data-testid="receive_message"]').last.evaluate(
            """
            (node) => Array.from(node.querySelectorAll('a'))
              .map((link) => ({
                title: (link.innerText || '').trim(),
                url: link.href || '',
              }))
              .filter((item) => item.url)
            """
        )
        return self._merge_references(data, [])

    def _merge_references(self, primary: list[dict[str, str]], secondary: list[dict[str, str]]) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen = set()
        for source in (primary, secondary):
            for item in source:
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                merged.append({"title": title or url, "url": url})
        return merged

    def _select_candidate_text(self, current_texts: list[str], baseline_texts: list[str]) -> str:
        if len(current_texts) > len(baseline_texts):
            return current_texts[-1]
        if current_texts and baseline_texts and current_texts[-1] != baseline_texts[-1]:
            return current_texts[-1]
        return ""

    async def _get_latest_receive_message(self, page):
        receive_messages = page.locator('[data-testid="receive_message"]')
        receive_count = await receive_messages.count()
        return receive_messages.nth(receive_count - 1) if receive_count else None

    async def _inspect_response_controls(self, page, latest_receive) -> dict[str, Any]:
        stop_buttons = page.locator('button:has-text("\u505c\u6b62\u751f\u6210")')
        stop_visible = await stop_buttons.count() > 0
        if latest_receive is None:
            return {
                "action_bar_visible": False,
                "regenerate_visible": False,
                "copy_visible": False,
                "stop_button_visible": stop_visible,
            }
        action_bar = latest_receive.locator('[data-testid="message_action_bar"]')
        regenerate = latest_receive.locator('[data-testid="message_action_regenerate"]')
        copy_button = latest_receive.locator('[data-testid="message_action_copy"]')
        return {
            "action_bar_visible": await action_bar.count() > 0,
            "regenerate_visible": await regenerate.count() > 0,
            "copy_visible": await copy_button.count() > 0,
            "stop_button_visible": stop_visible,
        }

    async def _is_response_complete(self, page, latest_receive, stable_hits: int, controls: dict[str, Any] | None = None) -> bool:
        if latest_receive is None:
            return False
        signals = controls or await self._inspect_response_controls(page, latest_receive)
        if signals.get("stop_button_visible"):
            return False
        if not signals.get("action_bar_visible"):
            return False
        return stable_hits >= 2
    async def _wait_for_settled_response_text(self, page, hinted: str) -> str:
        best = self._sanitize_response_text(hinted)
        stable = best
        stable_hits = 0
        deadline = asyncio.get_event_loop().time() + 12

        while asyncio.get_event_loop().time() < deadline:
            await self._raise_for_login_barrier(page)
            latest = self._sanitize_response_text(await self._extract_latest_response_text(page))
            if latest and len(latest) >= len(best):
                best = latest

            if latest and latest == stable:
                stable_hits += 1
            else:
                stable = latest
                stable_hits = 1 if latest else 0

            latest_receive = await self._get_latest_receive_message(page)
            controls = await self._inspect_response_controls(page, latest_receive)
            if best and stable_hits >= 2 and await self._is_response_complete(page, latest_receive, stable_hits, controls):
                return best

            await page.wait_for_timeout(1000)

        return best
    def _clean_serialized_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned: list[dict[str, Any]] = []
        for block in blocks:
            block_type = block.get("type")
            if block_type in {"paragraph", "heading", "blockquote"}:
                text = self._sanitize_response_text(str(block.get("text", "")))
                if not text:
                    continue
                if self._looks_like_interactive_tail(text):
                    continue
                cleaned.append({**block, "text": text})
                continue
            if block_type == "list":
                items = [self._sanitize_response_text(str(item)) for item in block.get("items", [])]
                items = [item for item in items if item and not self._looks_like_interactive_tail(item)]
                if not items:
                    continue
                cleaned.append({**block, "items": items})
                continue
            if block_type == "code_block":
                code = str(block.get("code", "")).rstrip()
                if not code:
                    continue
                cleaned.append({**block, "code": code})
                continue

        normalized: list[dict[str, Any]] = []
        for index, block in enumerate(cleaned):
            if (
                block.get("type") == "paragraph"
                and index + 1 < len(cleaned)
                and cleaned[index + 1].get("type") == "code_block"
                and self._looks_like_code_toolbar(str(block.get("text", "")))
            ):
                continue
            normalized.append(block)

        while normalized and normalized[-1].get("type") in {"paragraph", "blockquote"} and self._looks_like_interactive_tail(
            str(normalized[-1].get("text", ""))
        ):
            normalized.pop()
        return normalized

    def _is_structured_result_trustworthy(self, content: str, blocks: list[dict[str, Any]], settled_text: str) -> bool:
        if not content:
            return False
        if settled_text and len(content) < max(40, int(len(settled_text) * 0.7)):
            return False
        if settled_text and not blocks:
            return False
        if self._has_interactive_tail(content):
            return False
        if blocks and self._block_has_interactive_tail(blocks[-1]):
            return False
        if any(block.get("type") == "heading" and str(block.get("text", "")).strip() == "\u603b\u7ed3" for block in blocks):
            has_code = any(block.get("type") == "code_block" for block in blocks)
            has_list = any(block.get("type") == "list" for block in blocks)
            if has_list and not has_code and content.count("\n") < 2:
                return False
        return True

    def _is_copy_result_trustworthy(self, content: str, settled_text: str) -> bool:
        if not content:
            return False
        if settled_text and len(content) < max(40, int(len(settled_text) * 0.7)):
            return False
        if self._has_interactive_tail(content):
            return False
        return True

    def _clean_copy_text(self, text: str) -> str:
        cleaned = self._sanitize_response_text(text)
        cleaned = self._clean_markdown_tail(cleaned)
        return cleaned.strip()

    def _block_has_interactive_tail(self, block: dict[str, Any]) -> bool:
        block_type = block.get("type")
        if block_type in {"paragraph", "blockquote", "heading"}:
            return self._looks_like_interactive_tail(str(block.get("text", "")))
        if block_type == "list":
            items = [str(item) for item in block.get("items", [])]
            return bool(items and self._looks_like_interactive_tail(items[-1]))
        return False

    def _has_interactive_tail(self, content: str) -> bool:
        stripped = content.strip()
        if not stripped:
            return False
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if not lines:
            return False
        return self._looks_like_interactive_tail(lines[-1])
    async def _extract_via_copy(self, page, latest_receive) -> str:
        if latest_receive is None:
            return ""
        copy_button = latest_receive.locator('[data-testid="message_action_copy"]').first
        try:
            if not await copy_button.count():
                return ""
            origin = urlsplit(page.url).scheme + '://' + urlsplit(page.url).netloc
            if page.context is not None:
                await page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
            await copy_button.click(timeout=3000)
            await page.wait_for_timeout(500)
            text = await page.evaluate(
                """
                async () => {
                  try {
                    return (await navigator.clipboard.readText()) || '';
                  } catch (error) {
                    return '';
                  }
                }
                """
            )
            return str(text or "")
        except Exception:
            return ""

    def _render_blocks_to_markdown(self, blocks: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for block in blocks:
            block_type = block.get("type")
            if block_type == "heading":
                level = min(max(int(block.get("level", 1)), 1), 3)
                parts.append(f"{'#' * level} {str(block.get('text', '')).strip()}")
            elif block_type == "paragraph":
                parts.append(str(block.get("text", "")).strip())
            elif block_type == "blockquote":
                text = str(block.get("text", "")).strip()
                parts.append("\n".join(f"> {line}" if line else ">" for line in text.splitlines()))
            elif block_type == "list":
                ordered = bool(block.get("ordered", False))
                lines = []
                for index, item in enumerate(block.get("items", []), start=1):
                    prefix = f"{index}. " if ordered else "- "
                    lines.append(f"{prefix}{str(item).strip()}")
                if lines:
                    parts.append("\n".join(lines))
            elif block_type == "code_block":
                language = str(block.get("language", "")).strip()
                code = str(block.get("code", "")).rstrip("\n")
                fence = f"```{language}" if language else "```"
                parts.append(f"{fence}\n{code}\n```")
        return "\n\n".join(part for part in parts if part).strip()

    def _clean_markdown_tail(self, content: str) -> str:
        cleaned = content.strip()
        if not cleaned:
            return ""
        markers = [
            "\n\u9700\u8981\u6211\u628a",
            "\nHow can I",
            "\nCan I use",
            "\nWhat if I want",
            "\nWould you like me",
            "\nWould you like a",
            "\nWould you like these",
            "\nDo you want me",
            "\nShould I",
            "\n\u7528\u4e00\u53e5\u8bdd\u6982\u62ec",
            "\nOpenAI\u5b98\u7f51\u7684\u5408\u4f5c\u6848\u4f8b",
            "\n\u4ecb\u7ecd\u4e00\u4e0bOpenAI\u7684\u5b89\u5168\u529f\u80fd",
        ]
        for marker in markers:
            position = cleaned.find(marker)
            if position > 0:
                cleaned = cleaned[:position].rstrip()
        return cleaned

    def _looks_like_interactive_tail(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        prefixes = (
            "\u9700\u8981\u6211",
            "How can I",
            "Can I use",
            "What if I want",
            "Would you like me",
            "Would you like a",
            "Would you like these",
            "Do you want me",
            "Should I",
            "\u7528\u4e00\u53e5\u8bdd\u6982\u62ec",
            "OpenAI\u5b98\u7f51\u7684",
            "\u4ecb\u7ecd\u4e00\u4e0bOpenAI\u7684\u5b89\u5168\u529f\u80fd",
            "\u53c2\u8003 ",
        )
        return stripped.startswith(prefixes)

    def _looks_like_code_toolbar(self, text: str) -> bool:
        compact = " ".join(text.split()).strip().lower()
        if not compact:
            return True
        toolbar_tokens = {"python", "javascript", "typescript", "bash", "shell", "sql", "json", "yaml", "xml", "html", "css", "\u8fd0\u884c", "\u590d\u5236", "\u9884\u89c8"}
        parts = compact.split()
        return len(parts) <= 3 and all(part in toolbar_tokens for part in parts)

    def _sanitize_response_text(self, text: str) -> str:
        sanitized = text.strip()
        if not sanitized:
            return ""

        suggestion_markers = [
            "\n\u7528\u7b80\u6d01\u7684\u8bed\u8a00\u4ecb\u7ecd\u4e00\u4e0b",
            "\nOpenAI\u5b98\u7f51\u9996\u9875\u7684",
            "\n\u5982\u4f55\u5229\u7528OpenAI\u7684\u4f01\u4e1a\u89e3\u51b3\u65b9\u6848",
            "\n\u9700\u8981\u6211\u5e2e\u4f60\u6574\u7406",
            "\nWould you like me",
            "\nWould you like a",
            "\nWould you like these",
            "\nDo you want me",
            "\nShould I",
            "\n\u53c2\u8003 ",
        ]
        for marker in suggestion_markers:
            position = sanitized.find(marker)
            if position > 0:
                sanitized = sanitized[:position].rstrip()

        sanitized = re.sub(r"(https?://[^\s]+?)([A-Z][A-Za-z0-9._-]*)$", r"\1", sanitized)
        sanitized = re.sub(r"([\u4e00-\u9fffA-Za-z0-9])OpenAI\u3002", r"\1 OpenAI?", sanitized)
        return sanitized.strip()







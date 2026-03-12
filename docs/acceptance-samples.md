# Acceptance Samples

This file freezes the v1 acceptance samples for the default CDP path.

## 1. Short Answer

Prompt:

```text
Reply with exactly OK.
```

Expected:
- `/chat.status = ok`
- `content_markdown = OK`
- `diagnostics.extraction_path = structured`

## 2. Long Answer

Prompt:

```text
Write exactly five sentences in English explaining why a browser-driven model adapter can be useful for internal workflow automation.
```

Expected:
- `/chat.status = ok`
- `content_markdown` contains 5 complete sentences
- no obvious truncation
- `blocks` contains a list-like structure

## 3. Web Answer

Prompt:

```text
Please browse https://openai.com/ and give me exactly two short bullet points in Chinese summarizing the homepage. Then add one source link.
```

Expected:
- `/chat.status = ok`
- `content_markdown` contains 2 Chinese bullet points
- `usage_like_meta.references` is non-empty
- `diagnostics.extraction_path = structured`

## 4. Code Block Answer

Prompt:

```text
Return a Python function named add that takes two integers and returns their sum. Respond with a fenced code block, then a short two-item bullet list explaining the function.
```

Expected:
- `/chat.status = ok`
- `content_markdown` contains a fenced Python code block
- `blocks` contains `code_block`
- code block should not be replaced by toolbar text such as "python / run"

## 5. Markdown List Answer

Prompt:

```text
Give me a Markdown bullet list with exactly three Chinese points explaining why a unified web-model adapter is useful for enterprise systems.
```

Expected:
- `/chat.status = ok`
- `content_markdown` contains 3 bullet points
- `blocks` contains `list`
- no obvious truncation

from __future__ import annotations

import unittest
from pathlib import Path

from web_adapter.config import Settings
from web_adapter.providers.doubao import DoubaoProvider


class DoubaoMarkdownTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = Settings(
            mock_mode=True,
            artifact_dir=Path("tmp_test_provider") / "artifacts",
            master_profile_dir=Path("tmp_test_provider") / "master",
            runtime_profile_root=Path("tmp_test_provider") / "runtime",
        )
        self.provider = DoubaoProvider(settings)

    def test_render_blocks_to_markdown_preserves_core_formats(self) -> None:
        blocks = [
            {"type": "heading", "level": 2, "text": "Summary"},
            {"type": "paragraph", "text": "A **bold** line with [link](https://example.com)."},
            {"type": "blockquote", "text": "Quoted line\nSecond line"},
            {"type": "list", "ordered": False, "items": ["one", "two"]},
            {"type": "code_block", "language": "python", "code": "def add(a, b):\n    return a + b"},
        ]

        markdown = self.provider._render_blocks_to_markdown(blocks)

        self.assertIn("## Summary", markdown)
        self.assertIn("> Quoted line\n> Second line", markdown)
        self.assertIn("- one\n- two", markdown)
        self.assertIn("```python\ndef add(a, b):\n    return a + b\n```", markdown)

    def test_clean_serialized_blocks_drops_interactive_tail(self) -> None:
        blocks = [
            {"type": "paragraph", "text": "OpenAI official site: [OpenAI](https://openai.com/)"},
            {"type": "paragraph", "text": "\u9700\u8981\u6211\u628a\u8fd9\u4e24\u53e5\u603b\u7ed3\u6269\u5c55\u6210\u4e00\u6bb5\u5b8c\u6574\u7684\u4ecb\u7ecd\u5417\uff1f"},
        ]

        cleaned = self.provider._clean_serialized_blocks(blocks)

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["text"], "OpenAI official site: [OpenAI](https://openai.com/)")

    def test_clean_markdown_tail_removes_follow_up_questions(self) -> None:
        content = (
            "First paragraph.\n\n"
            "Second paragraph.\n"
            "How can I test this function?\n"
            "Can I use this function with other data types?"
        )

        cleaned = self.provider._clean_markdown_tail(content)

        self.assertEqual(cleaned, "First paragraph.\n\nSecond paragraph.")

    def test_clean_serialized_blocks_drops_code_toolbar_paragraph(self) -> None:
        blocks = [
            {"type": "paragraph", "text": "python\n运行"},
            {"type": "code_block", "language": "python", "code": "def add(a, b):\n    return a + b"},
        ]

        cleaned = self.provider._clean_serialized_blocks(blocks)

        self.assertEqual(cleaned, [{"type": "code_block", "language": "python", "code": "def add(a, b):\n    return a + b"}])

    def test_structured_result_trustworthy_requires_reasonable_length(self) -> None:
        self.assertFalse(
            self.provider._is_structured_result_trustworthy(
                "short answer",
                [{"type": "paragraph", "text": "short answer"}],
                "This is a much longer settled response that should not be replaced by a tiny truncated extraction.",
            )
        )
        self.assertTrue(
            self.provider._is_structured_result_trustworthy(
                "This is a complete structured response that is comfortably long enough to pass the trust threshold.",
                [{"type": "paragraph", "text": "This is a complete structured response that is comfortably long enough to pass the trust threshold."}],
                "This is a complete structured response that is comfortably long enough to pass the trust threshold.",
            )
        )

    def test_copy_result_trustworthy_requires_reasonable_length(self) -> None:
        self.assertFalse(
            self.provider._is_copy_result_trustworthy(
                "tiny",
                "This settled response is much longer than the clipboard fallback and should win.",
            )
        )
        self.assertTrue(
            self.provider._is_copy_result_trustworthy(
                "Clipboard fallback returned the full answer body.",
                "Clipboard fallback returned the full answer body.",
            )
        )



if __name__ == "__main__":
    unittest.main()



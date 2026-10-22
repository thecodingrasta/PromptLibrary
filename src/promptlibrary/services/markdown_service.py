"""Render Markdown as content, never as executable HTML or template code."""

from html import escape
from urllib.parse import urlsplit

import mistune
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound


class PromptRenderer(mistune.HTMLRenderer):
    def __init__(self) -> None:
        super().__init__(escape=True, allow_harmful_protocols=False)

    def safe_url(self, url: str) -> str:
        # Remove control characters before checking schemes, including entity-decoded links.
        cleaned = "".join(character for character in url if ord(character) > 32)
        try:
            parsed = urlsplit(cleaned)
        except ValueError:
            return "#blocked-link"
        if parsed.scheme.lower() not in {"", "https", "http", "mailto"}:
            return "#blocked-link"
        if cleaned.startswith("//"):
            return "#blocked-link"
        return escape(cleaned, quote=True)

    def image(self, text: str, url: str, title: str | None = None) -> str:
        # Remote image requests can disclose when a private prompt is viewed.
        return '<span class="image-description">[Image: ' + escape(text) + "]</span>"

    def block_code(self, code: str, info: str | None = None) -> str:
        language = (info or "").strip().split(maxsplit=1)[0] if (info or "").strip() else "text"
        try:
            lexer = get_lexer_by_name(language)
            body = str(highlight(code, lexer, HtmlFormatter(nowrap=True)))
        except ClassNotFound:
            language = "text"
            body = escape(code)
        return (
            '<pre class="highlight"><code class="language-'
            + escape(language, quote=True)
            + '">'
            + body
            + "</code></pre>\n"
        )


def render_markdown(text: str) -> str:
    # A fresh parser avoids sharing mutable parsing state between concurrent requests.
    renderer = mistune.create_markdown(
        renderer=PromptRenderer(), plugins=["table", "strikethrough"]
    )
    return str(renderer(text))

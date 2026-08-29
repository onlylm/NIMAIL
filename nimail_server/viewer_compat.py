from __future__ import annotations

from datetime import datetime
from html import escape


def _local_wall_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return value.replace("T", " ")[:19]


def compatibility_cards_html(items: list[dict], recipient: str = "") -> str:
    """Expose the exact Layout-A markup consumed by LocalFlow's relay parser."""
    cards = []
    recipient_text = escape(recipient, quote=True)
    for item in items:
        sender = escape(str(item.get("sender") or ""), quote=True)
        subject = escape(str(item.get("subject") or ""), quote=True)
        received_at = escape(str(item.get("received_at") or ""), quote=True)
        relay_date = escape(_local_wall_time(str(item.get("received_at") or "")), quote=True)
        otp = escape(str(item.get("otp_code") or ""), quote=True)
        preview = escape(str(item.get("preview") or ""), quote=True)
        body = escape(str(item.get("body_text") or item.get("preview") or ""), quote=True)
        message_id = escape(str(item.get("id") or ""), quote=True)
        # LocalFlow uses strict regular expressions, so the class and child tags
        # below intentionally match its Layout A verbatim. Additional metadata is
        # included in body/meta text instead of altering the opening tag.
        cards.append(
            '<article class="mail-card">'
            f'<span class="subject">{subject}</span>'
            f'<span class="date">{relay_date}</span>'
            f'<div class="meta">发件人：{sender}</div>'
            f'<pre class="body">{body}</pre>'
            '</article>'
        )
    return ('<section id="nimail-compat-cards" hidden aria-hidden="true">'
            + "".join(cards) + '</section>')

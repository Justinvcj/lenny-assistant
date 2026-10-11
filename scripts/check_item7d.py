"""Item 7d inspection: message 44323b62-2977-443c-b69d-2bf971f8e269."""

import asyncio
import uuid
from app.db import async_session_factory
from app.models import Message

async def check():
    target_id = uuid.UUID("44323b62-2977-443c-b69d-2bf971f8e269")
    async with async_session_factory() as session:
        msg = await session.get(Message, target_id)
        if not msg:
            print(f"Message {target_id} NOT FOUND in DB.")
            return

        print(f"Message ID: {msg.id}")
        print(f"Role: {msg.role}")
        print(f"Intent: {msg.intent}")
        print(f"Latency: {msg.latency_ms} ms")
        print(f"Degraded: {msg.degraded}")
        print(f"\nContent:\n{msg.content}\n")
        print(f"Citations ({len(msg.citations)}):")
        for c in msg.citations:
            n = c.get("n")
            guest = c.get("guest")
            title = c.get("title")
            passage = (c.get("passage") or "")[:80]
            print(f"  [S{n}] Guest: {guest} | Title: {title} | Passage: {passage}...")

if __name__ == "__main__":
    asyncio.run(check())

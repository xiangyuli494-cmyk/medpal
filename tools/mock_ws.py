"""W1 临时 mock 会话服务：让 websocat 能打通协议。

依赖 websockets（见 requirements-dev.txt）。W3 由 Django Channels 接管后删除。

用法：
    python tools/mock_ws.py
    python tools/mock_ws.py --port 18090

自检：
    websocat ws://127.0.0.1:8090 -t
    粘贴 {"type":"key","session":"s_001","key":"GREEN_DOWN"}
"""
import argparse
import asyncio
import json

import websockets

TURN = {
    "type": "turn_result",
    "session": "s_001",
    "turn": 1,
    "caption": {"text": "2 楼检验科，出电梯往左", "emphasis": ["2 楼", "往左"]},
    "speech": {"audio_url": "", "rate": 0.86, "can_interrupt": True},
    "device": {"vibrate": "confirm_twice", "haptic_after_ms": 1200},
    "flow": {"step": "navigate", "step_index": 8, "total": 11, "why": "抽血要空腹"},
    "escalation": {"level": "none"},
    "confidence": {"asr": 0.91, "intent": 0.88},
}


async def handler(ws) -> None:
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("type") == "key":
            await ws.send(json.dumps(TURN, ensure_ascii=False))


async def main(port: int) -> None:
    async with websockets.serve(handler, "127.0.0.1", port):
        print(f"mock ws: ws://127.0.0.1:{port}")
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    asyncio.run(main(parser.parse_args().port))

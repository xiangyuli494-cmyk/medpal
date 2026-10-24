"""W1 临时 mock 会话服务：让 websocat 能打通协议。

依赖 websockets（见 requirements-dev.txt）。W3 由 Django Channels 接管后删除。

协议来源：docs/api/ws-protocol.md（v0.1）。本文件只实现其中用于自检的最小子集：
  - session.hello  → session.ready
  - touch.event    → turn_result（target 取设备端触摸控件标识符）
  - text.input     → turn_result
  - ping           → pong
  - ack            → 静默记录，不回复
  - resend         → 静默忽略（mock 不缓存帧）

用法：
    python tools/mock_ws.py
    python tools/mock_ws.py --port 18090

自检：
    websocat ws://127.0.0.1:8090 -t
    {"type":"session.hello","protocol_version":"0.4","device_id":"dev_001","episode_id":"ep_001","client":"device","accessibility_mode":"elder"}
    {"type":"touch.event","session":"s_001","target":"primary","action":"tap"}
    {"type":"ping"}
"""

import argparse
import asyncio
import json

import websockets

PROTOCOL_VERSION = "0.4"

TURN = {
    "type": "turn_result",
    "session": "s_001",
    "turn": 1,
    "caption": {"text": "2 楼检验科，出电梯往左", "emphasis": ["2 楼", "往左"]},
    "speech": {"audio_url": "", "rate": 0.86, "can_interrupt": True},
    "device": {"vibrate": "confirm_twice", "haptic_after_ms": 1200},
    "flow": {"step": "NAVIGATE", "step_index": 8, "total": 11, "why": "抽血要空腹"},
    "escalation": {"level": "none"},
    "confidence": {"asr": 0.91, "intent": 0.88},
    "primary_label": "我到了",
}

READY = {
    "type": "session.ready",
    "session_id": "s_001",
    "episode_id": "ep_001",
    "protocol_version": PROTOCOL_VERSION,
    "state": "NAVIGATE",
}


async def handler(ws) -> None:
    async for raw in ws:
        if isinstance(raw, (bytes, bytearray)):
            # 二进制音频帧：mock 不处理音频，只确认收到。
            continue
        msg = json.loads(raw)
        kind = msg.get("type")

        if kind == "session.hello":
            await ws.send(json.dumps(READY, ensure_ascii=False))
        elif kind == "ping":
            await ws.send(json.dumps({"type": "pong"}, ensure_ascii=False))
        elif kind in ("touch.event", "text.input"):
            await ws.send(json.dumps(TURN, ensure_ascii=False))
        # ack / resend / control.barge_in / task.confirm：mock 静默接受，不回复。


async def main(host: str, port: int) -> None:
    async with websockets.serve(handler, host, port):
        print(f"mock ws: ws://{host}:{port}")
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1", help="监听地址；局域网访问用 0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port))

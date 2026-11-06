"""Opt-in live MCP smoke check: writes a draft, NEVER publishes.

Usage: python scripts/check_board_draft.py --room NAME --live
Leave the target chat open and its board editor empty (or the same test draft).
"""
import argparse
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BODY = "톡게시판 MCP 기능 테스트\n한글과 줄바꿈 입력을 확인합니다.\n실제 등록하지 않는 초안입니다."


async def main(room):
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "kakao_mcp"])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = {tool.name for tool in (await client.list_tools()).tools}
            assert {"kakao_prepare_board_post", "kakao_get_board_draft"} <= tools

            async def call(name, arguments):
                result = await client.call_tool(name, arguments)
                assert not result.isError, result
                data = result.structuredContent
                if data is None:
                    data = json.loads(next(c.text for c in result.content if c.type == "text"))
                return data.get("result", data)

            first = await call("kakao_prepare_board_post", {"room_name": room, "body": BODY})
            assert first.get("success"), first
            assert first["published"] is False and first["body"] == BODY
            retry = await call("kakao_prepare_board_post", {"room_name": room, "body": BODY})
            assert retry.get("success") and retry["body"] == BODY, retry
            conflict = await call("kakao_prepare_board_post", {"room_name": room, "body": "덮어쓰면 안 되는 본문"})
            assert conflict["success"] is False, conflict
            status = await call("kakao_get_board_draft", {"room_name": room})
            assert status.get("body") == BODY, status
            print(json.dumps({"tools_registered": True, "draft_verified": True,
                              "retry_verified": True, "existing_draft_preserved": True,
                              "published": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required to interact with KakaoTalk")
    asyncio.run(main(args.room))

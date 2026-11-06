"""Live read/search/draft/publish-preflight check. NEVER calls the publish tool."""
import argparse
import asyncio
import json
import sys
import time
import tomllib
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BODY = "톡게시판 MCP 등록 준비 테스트\n읽기·검색·등록 전 검증을 확인합니다.\n이 글은 실제 등록하지 않습니다."


async def main(room, query, read_index=0, max_posts=3, config=None, expect_match=False):
    if config:
        entry = tomllib.loads(Path(config).read_text(encoding="utf-8-sig"))["mcp_servers"]["kakaotalk"]
        params = StdioServerParameters(command=entry["command"], args=entry["args"],
                                       cwd=entry.get("cwd"), env=entry.get("env"))
    else:
        params = StdioServerParameters(command=sys.executable, args=["-m", "kakao_mcp"])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert {"kakao_read_board_post", "kakao_search_board_posts",
                    "kakao_prepare_board_publish", "kakao_check_board_publish",
                    "kakao_publish_board_post"} <= names

            async def call(name, args):
                # Hard stop independent of model instructions.
                if name == "kakao_publish_board_post":
                    raise AssertionError("Actual publication is forbidden in this script")
                result = await client.call_tool(name, args)
                assert not result.isError, result
                data = result.structuredContent
                if data is None:
                    data = json.loads(next(c.text for c in result.content if c.type == "text"))
                return data.get("result", data)

            read = await call("kakao_read_board_post", {"room_name": room, "index": read_index})
            assert read["success"] and read["body"], read
            start = time.perf_counter()
            search = await call("kakao_search_board_posts", {"room_name": room, "query": query, "max_posts": max_posts, "refresh": True})
            fresh_seconds = time.perf_counter() - start
            assert search["success"] and search["scanned"] > 0, search
            if expect_match:
                assert search["matches"], search
            start = time.perf_counter()
            cached = await call("kakao_search_board_posts", {"room_name": room, "query": query, "max_posts": max_posts})
            cached_seconds = time.perf_counter() - start
            assert cached["cache_hit"] and cached["matches"] == search["matches"], cached
            draft = await call("kakao_prepare_board_post", {"room_name": room, "body": BODY})
            assert draft["success"] and draft["published"] is False, draft
            preview = await call("kakao_prepare_board_publish", {"room_name": room})
            assert preview["success"] and preview["body"] == BODY, preview
            check = await call("kakao_check_board_publish", {"confirmation_token": preview["confirmation_token"]})
            assert check["ready"] and check["published"] is False, check
            print(json.dumps({"configured_server": bool(config), "tools_registered": True,
                              "read_verified": True, "search_scanned": search["scanned"],
                              "search_matches": len(search["matches"]), "publish_preflight_ready": True,
                              "fresh_search_seconds": round(fresh_seconds, 4),
                              "cached_search_seconds": round(cached_seconds, 4),
                              "actual_publish_called": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", required=True)
    parser.add_argument("--query", required=True, help="Text to look for in the test board")
    parser.add_argument("--read-index", type=int, default=0)
    parser.add_argument("--max-posts", type=int, default=3)
    parser.add_argument("--expect-match", action="store_true")
    parser.add_argument("--config")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live required")
    asyncio.run(main(args.room, args.query, args.read_index, args.max_posts, args.config, args.expect_match))

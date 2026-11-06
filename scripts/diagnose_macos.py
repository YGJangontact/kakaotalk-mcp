"""Read-only AX metadata inspection. Labels may contain private room/post text."""
import argparse
import json
from kakao_mcp.backends.macos import MacBoardDesktop

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", required=True)
    parser.add_argument("--include-labels", action="store_true")
    args = parser.parse_args()
    print(json.dumps(MacBoardDesktop().diagnose(args.room, args.include_labels), ensure_ascii=False, indent=2))

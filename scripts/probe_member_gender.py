"""探针：列出全部成员的 gender，确认平台性别字段的填充情况。"""
import json
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

chatroom_id = sys.argv[1]
origin = sys.argv[2] if len(sys.argv) > 2 else "https://www.ivorune.xyz"
input_json = quote(json.dumps({"json": {"chatroomId": chatroom_id, "limit": 1000}}))
url = f"{origin}/api/trpc/chatroom.getMembers?input={input_json}"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:19222")
    for context in browser.contexts:
        try:
            response = context.request.get(url)
        except Exception as error:
            print(f"context probe failed: {type(error).__name__}: {error}")
            continue
        print(f"status: {response.status}")
        if response.status != 200:
            print(response.text()[:300])
            continue
        body = response.json()
        data = body.get("result", {}).get("data", {}).get("json", body)
        members = data.get("members", []) if isinstance(data, dict) else []
        print(f"member_count: {len(members)}")
        for member in members:
            print(f"  {member.get('fullName')}  gender={member.get('gender')!r}  isBot={member.get('isBot')}")
        break

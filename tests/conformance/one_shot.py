"""A one-shot CLI for the conformance suite: it asks the model once about its goal, prints the answer and exits."""

import json
import os
import sys
import urllib.request

goal = sys.argv[1]
request = urllib.request.Request(
    f"{os.environ['OPENAI_BASE_URL']}/chat/completions",
    json.dumps({"model": "fake-model", "messages": [{"role": "user", "content": goal}]}).encode(),
    {"content-type": "application/json", "authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(request) as reply:
    print(json.load(reply)["choices"][0]["message"]["content"])

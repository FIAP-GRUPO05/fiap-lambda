"""Exercise the real Lambda runtime locally and verify captured MIME messages."""
import json
import time
import urllib.error
import urllib.request
import uuid

RUNTIME = "http://127.0.0.1:19000/2015-03-31/functions/function/invocations"
MAILBOX = "http://127.0.0.1:18025/api/v2/messages"


def request(url, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=body,
            headers={"Content-Type": "application/json"}), timeout=20) as response:
        return json.load(response)


for attempt in range(30):
    try:
        assert request(RUNTIME, {"operation": "health"})["ready"]
        break
    except (OSError, AssertionError):
        if attempt == 29:
            raise
        time.sleep(1)
run = str(uuid.uuid4())
for html in (False, True):
    result = request(RUNTIME, {"to": "local@example.test", "subject": "OS local " + run,
        "body": "<p>Ordem de servico concluida</p>" if html else "Ordem de servico concluida",
        "html": html, "correlationId": run})
    assert result["statusCode"] == 200 and result["messageId"]
messages = [item for item in request(MAILBOX)["items"]
            if item["Content"]["Headers"].get("X-Correlation-Id") == [run]]
assert len(messages) == 2, "Expected both notification messages in MailHog"
assert {item["Content"]["Headers"]["Content-Type"][0].split(";")[0]
        for item in messages} == {"text/plain", "text/html"}
print(json.dumps({"status": "passed", "runtime": "AWS Lambda RIE", "transport": "local SMTP",
                  "messages": len(messages), "correlationId": run}))

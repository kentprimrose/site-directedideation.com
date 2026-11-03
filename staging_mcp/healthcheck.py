"""Check the local HTTP authentication boundary without credentials."""

from http.client import HTTPConnection

conn = HTTPConnection("127.0.0.1", 8765, timeout=3)
try:
    conn.request("POST", "/mcp", headers={"Host": "mcp-staging.directedideation.com"})
    response = conn.getresponse()
    if response.status != 401:
        raise SystemExit(1)
finally:
    conn.close()

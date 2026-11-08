import asyncio
import unittest
from agentsteers.http_auth import LoopbackBearerGuard

TOKEN = "not-a-production-secret-" + "x" * 40

async def probe(headers):
    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    guard = LoopbackBearerGuard(downstream, TOKEN)
    events = []
    async def send(msg): events.append(msg)
    async def receive(): return {"type": "http.request", "body": b"", "more_body": False}
    await guard({"type": "http", "headers": headers, "method": "POST", "path": "/mcp"}, receive, send)
    return events[0]["status"]

class HTTPAuthTests(unittest.TestCase):
    def run_probe(self, host=b"localhost:8765", authorization=None, origin=None):
        hs = [(b"host", host)]
        if authorization is not None: hs.append((b"authorization", authorization))
        if origin is not None: hs.append((b"origin", origin))
        return asyncio.run(probe(hs))

    def test_denies_missing_token(self):
        self.assertEqual(self.run_probe(), 401)

    def test_denies_wrong_token(self):
        self.assertEqual(self.run_probe(authorization=b"Bearer wrong"), 401)

    def test_accepts_correct_token(self):
        self.assertEqual(self.run_probe(authorization=("Bearer "+TOKEN).encode()), 200)

    def test_denies_external_host(self):
        self.assertEqual(self.run_probe(host=b"example.com", authorization=("Bearer "+TOKEN).encode()), 403)

    def test_denies_untrusted_origin(self):
        self.assertEqual(self.run_probe(authorization=("Bearer "+TOKEN).encode(), origin=b"https://evil.example"), 403)

    def test_rejects_weak_configuration(self):
        with self.assertRaises(ValueError): LoopbackBearerGuard(None, "abc")

if __name__ == "__main__":
    unittest.main()

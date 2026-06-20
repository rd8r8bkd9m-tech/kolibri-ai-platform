import unittest
from pathlib import Path
import sys
import types


class _FastAPIStub:
    def __init__(self, *args, **kwargs):
        pass

    def add_middleware(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return self._decorator

    def post(self, *args, **kwargs):
        return self._decorator

    def delete(self, *args, **kwargs):
        return self._decorator

    def websocket(self, *args, **kwargs):
        return self._decorator

    @staticmethod
    def _decorator(func):
        return func


fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.FastAPI = _FastAPIStub
fastapi_stub.Request = object
fastapi_stub.WebSocket = object
fastapi_stub.WebSocketDisconnect = Exception
middleware_stub = types.ModuleType("fastapi.middleware")
cors_stub = types.ModuleType("fastapi.middleware.cors")
cors_stub.CORSMiddleware = object
sys.modules.setdefault("fastapi", fastapi_stub)
sys.modules.setdefault("fastapi.middleware", middleware_stub)
sys.modules.setdefault("fastapi.middleware.cors", cors_stub)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from public_proxy import latest_user_message, message_from_payload


class PublicProxyPayloadTests(unittest.TestCase):
    def test_message_from_direct_message(self):
        self.assertEqual(message_from_payload({"message": " ping "}), "ping")

    def test_message_from_chat_messages(self):
        payload = {
            "messages": [
                {"role": "system", "content": "ignore"},
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "answer"},
                {"role": "user", "content": "latest"},
            ]
        }
        self.assertEqual(message_from_payload(payload), "latest")

    def test_message_from_payload_ignores_malformed_messages(self):
        self.assertEqual(message_from_payload({"messages": ["bad", None]}), "")

    def test_latest_user_message_falls_back_to_last_message(self):
        self.assertEqual(latest_user_message([{"role": "assistant", "content": "fallback"}]), "fallback")


if __name__ == "__main__":
    unittest.main()

"""Fake Plex on 127.0.0.1:<port> for the emulator QA; answers from tests/fixtures/plex/ through FakePMS."""
from __future__ import annotations

import http.server
import sys

sys.path.insert(0, sys.argv[1])
from tests.fake_pms import FakePMS  # noqa: E402
from tests.fake_plex_http import _FakePlexHandler  # noqa: E402


class _Fake:
    pass


class _LoggingHandler(_FakePlexHandler):
    def _route(self, method: str) -> None:
        print(method, self.path, flush=True)
        super()._route(method)


fake = _Fake()
fake.pms = FakePMS()
fake.requests = []
server = http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2])), _LoggingHandler)
server.fake = fake
print("listening", server.server_address, flush=True)
server.serve_forever()

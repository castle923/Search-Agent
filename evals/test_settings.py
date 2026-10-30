import http.client
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from http.server import HTTPServer
from dotenv import dotenv_values
import web


class SettingsTests(unittest.TestCase):
    def test_save_and_reject_untrusted_requests(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ):
            path = Path(folder) / '.env'
            path.write_text('DRY_RUN=1\nMAIL_TO=test@example.com\n', encoding='utf-8')
            with patch.object(web, 'ENV_FILE', path):
                server = HTTPServer(('127.0.0.1', 0), web.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                host = f'127.0.0.1:{server.server_port}'

                def request(method, route, body=None, origin=None):
                    conn = http.client.HTTPConnection(host)
                    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                    if origin:
                        headers['Origin'] = origin
                    conn.request(method, route, body, headers)
                    response = conn.getresponse()
                    result = response.status, response.read(), dict(response.getheaders())
                    conn.close()
                    return result

                try:
                    key = 'sk-ant-local-test-not-a-real-key'
                    form = urlencode({'token': web.SETTINGS_TOKEN, 'api_key': key})
                    before = path.read_text()
                    self.assertEqual(request('POST', '/settings', form, 'https://attacker.example')[0], 403)
                    self.assertEqual(request('POST', '/settings', form)[0], 403)
                    self.assertEqual(path.read_text(), before)
                    bad = urlencode({'token': 'wrong', 'api_key': key})
                    self.assertEqual(request('POST', '/settings', bad, f'http://{host}')[0], 403)
                    bad = urlencode({'token': '잘못된 토큰', 'api_key': key})
                    self.assertEqual(request('POST', '/settings', bad, f'http://{host}')[0], 403)
                    self.assertEqual(request('POST', '/settings', form, f'http://{host}')[0], 303)
                    values = dotenv_values(path)
                    self.assertEqual(values['ANTHROPIC_API_KEY'], key)
                    self.assertEqual(values['DRY_RUN'], '1')
                    self.assertEqual(values['MAIL_TO'], 'test@example.com')
                    self.assertEqual(os.environ['ANTHROPIC_API_KEY'], key)
                    status, body, headers = request('GET', '/settings')
                    self.assertEqual(status, 200)
                    self.assertNotIn(key.encode(), body)
                    self.assertEqual(headers['Cache-Control'], 'no-store')
                    self.assertIn(b'type="password"', body)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


if __name__ == '__main__':
    unittest.main()

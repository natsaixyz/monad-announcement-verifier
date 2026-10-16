"""HTTP smoke tests: no network access to GitHub is required."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import Handler


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=5)

    def test_home_and_health(self):
        with urllib.request.urlopen(self.base + '/') as r:
            self.assertIn(b'Know it', r.read())
            self.assertIn('Content-Security-Policy', r.headers)
        with urllib.request.urlopen(self.base + '/health') as r:
            self.assertEqual(json.load(r)['status'], 'ok')

    def test_rejects_unsafe_url(self):
        req = urllib.request.Request(self.base + '/api/verify', data=json.dumps({'url': 'https://evil.example'}).encode(), headers={'Content-Type':'application/json'}, method='POST')
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertEqual(err.exception.code, 400)

    def test_successful_api_result(self):
        fixture = {'ok': True, 'number': 1, 'signers': ['TEST'], 'message': 'signed test'}
        req = urllib.request.Request(self.base + '/api/verify', data=json.dumps({'url':'mf-1'}).encode(), headers={'Content-Type':'application/json'}, method='POST')
        with patch('app.verify_announcement', return_value=fixture) as verify:
            with urllib.request.urlopen(req) as response:
                self.assertEqual(json.load(response), fixture)
            verify.assert_called_once()
            self.assertEqual(verify.call_args.args[0], 1)

if __name__ == '__main__':
    unittest.main()

import os
import socket
import unittest
from unittest import mock

from dockctl.gateway import DEFAULT_GATEWAY, GatewayError, dock_status, gateway_url, list_docks
from tests.fakegateway import FakeGateway


class GatewayUrlTest(unittest.TestCase):
    def test_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(gateway_url(), DEFAULT_GATEWAY)

    def test_environment(self):
        with mock.patch.dict(os.environ, {"DOCKCTL_GATEWAY": "http://gw.example:8470/"}):
            self.assertEqual(gateway_url(), "http://gw.example:8470")

    def test_override_wins(self):
        with mock.patch.dict(os.environ, {"DOCKCTL_GATEWAY": "http://gw.example:8470"}):
            self.assertEqual(gateway_url("http://127.0.0.1:9000"), "http://127.0.0.1:9000")


class ClientTest(unittest.TestCase):
    def test_list_docks(self):
        with FakeGateway({"D-0002": (1, 2), "D-0001": (3, 4)}) as gw:
            self.assertEqual([d for d, _ in list_docks(gw.url)], ["D-0001", "D-0002"])

    def test_dock_status(self):
        with FakeGateway({"D-0001": (3, 9)}) as gw:
            status = dock_status(gw.url, "D-0001")
        self.assertEqual((status["id"], status["bikes"], status["free"]), ("D-0001", 3, 9))

    def test_error_status(self):
        with FakeGateway({}, errors={"D-0004": 502}) as gw:
            with self.assertRaises(GatewayError) as caught:
                dock_status(gw.url, "D-0004")
        self.assertEqual(caught.exception.status, 502)

    def test_unknown_dock(self):
        with FakeGateway({"D-0001": (3, 9)}) as gw:
            with self.assertRaises(GatewayError) as caught:
                dock_status(gw.url, "D-0999")
        self.assertEqual(caught.exception.status, 404)

    def test_unreachable(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(GatewayError) as caught:
            list_docks(f"http://127.0.0.1:{port}")
        self.assertIsNone(caught.exception.status)


if __name__ == "__main__":
    unittest.main()

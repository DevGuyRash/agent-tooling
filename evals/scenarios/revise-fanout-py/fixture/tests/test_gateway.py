import os
import socket
import unittest
from unittest import mock

from coldctl.gateway import DEFAULT_GATEWAY, GatewayError, NoAnswer, gateway_url, list_units, unit_reading
from tests.fakegateway import FakeGateway


class GatewayUrlTest(unittest.TestCase):
    def test_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(gateway_url(), DEFAULT_GATEWAY)

    def test_environment(self):
        with mock.patch.dict(os.environ, {"COLDCTL_GATEWAY": "http://bms-gw.example:8640/"}):
            self.assertEqual(gateway_url(), "http://bms-gw.example:8640")

    def test_override_wins(self):
        with mock.patch.dict(os.environ, {"COLDCTL_GATEWAY": "http://bms-gw.example:8640"}):
            self.assertEqual(gateway_url("http://127.0.0.1:9000"), "http://127.0.0.1:9000")


class ClientTest(unittest.TestCase):
    def test_list_units(self):
        with FakeGateway({"U-0002": (1.0, 2.0), "U-0001": (3.0, 4.0)}) as gw:
            self.assertEqual(sorted(u for u, _ in list_units(gw.url)), ["U-0001", "U-0002"])

    def test_unit_reading(self):
        with FakeGateway({"U-0001": (-19.4, -20.0)}) as gw:
            reading = unit_reading(gw.url, "U-0001")
        self.assertEqual((reading["id"], reading["temp_c"], reading["setpoint_c"]), ("U-0001", -19.4, -20.0))

    def test_error_status(self):
        with FakeGateway({}, errors={"U-0004": 502}) as gw:
            with self.assertRaises(GatewayError) as caught:
                unit_reading(gw.url, "U-0004")
        self.assertEqual(caught.exception.status, 502)

    def test_unknown_unit(self):
        with FakeGateway({"U-0001": (-19.4, -20.0)}) as gw:
            with self.assertRaises(GatewayError) as caught:
                unit_reading(gw.url, "U-0999")
        self.assertEqual(caught.exception.status, 404)

    def test_no_answer(self):
        with FakeGateway({}, silent={"U-0003"}) as gw:
            with self.assertRaises(NoAnswer):
                unit_reading(gw.url, "U-0003", timeout=0.3)

    def test_unreachable(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(GatewayError) as caught:
            list_units(f"http://127.0.0.1:{port}")
        self.assertIsNone(caught.exception.status)


if __name__ == "__main__":
    unittest.main()

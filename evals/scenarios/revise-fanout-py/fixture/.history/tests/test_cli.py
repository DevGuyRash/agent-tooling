import contextlib
import io
import os
import unittest
from unittest import mock

from coldctl.cli import describe, main
from tests.fakegateway import FakeGateway


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class DescribeTest(unittest.TestCase):
    def test_freezer(self):
        self.assertEqual(describe({"id": "U-0412", "temp_c": -19.4, "setpoint_c": -20.0, "defrost": False}),
                         "U-0412: -19.4 C (setpoint -20.0 C)")

    def test_whole_degrees(self):
        self.assertEqual(describe({"id": "U-0007", "temp_c": 3, "setpoint_c": 2, "defrost": False}),
                         "U-0007: 3.0 C (setpoint 2.0 C)")

    def test_defrost(self):
        self.assertEqual(describe({"id": "U-0007", "temp_c": 6.8, "setpoint_c": 3.0, "defrost": True}),
                         "U-0007: 6.8 C (setpoint 3.0 C), defrosting")


class CommandsTest(unittest.TestCase):
    def test_units_sorted(self):
        with FakeGateway({"U-0010": (1.0, 2.0), "U-0002": (1.0, 2.0)}) as gw:
            code, out, _ = run("--gateway", gw.url, "units")
        self.assertEqual(code, 0)
        self.assertEqual([line.split()[0] for line in out.splitlines()], ["U-0002", "U-0010"])

    def test_temp(self):
        with FakeGateway({"U-0001": (-18.2, -20.0), "U-0002": (3.4, 3.0)}) as gw:
            code, out, _ = run("--gateway", gw.url, "temp", "U-0002", "U-0001")
        self.assertEqual(code, 0)
        self.assertEqual(out, "U-0002: 3.4 C (setpoint 3.0 C)\nU-0001: -18.2 C (setpoint -20.0 C)\n")

    def test_temp_uses_environment(self):
        with FakeGateway({"U-0001": (2.5, 3.0)}) as gw, mock.patch.dict(os.environ, {"COLDCTL_GATEWAY": gw.url}):
            code, out, _ = run("temp", "U-0001")
        self.assertEqual((code, out), (0, "U-0001: 2.5 C (setpoint 3.0 C)\n"))

    def test_temp_error(self):
        with FakeGateway({}, errors={"U-0004": 500}) as gw:
            code, out, err = run("--gateway", gw.url, "temp", "U-0004")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("HTTP 500", err)


if __name__ == "__main__":
    unittest.main()

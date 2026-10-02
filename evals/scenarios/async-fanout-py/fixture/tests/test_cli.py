import contextlib
import io
import os
import unittest
from unittest import mock

from dockctl.cli import describe, main
from tests.fakegateway import FakeGateway


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class DescribeTest(unittest.TestCase):
    def test_plural(self):
        self.assertEqual(describe({"id": "D-0042", "bikes": 7, "free": 12}), "D-0042: 7 bikes, 12 free")

    def test_one_bike(self):
        self.assertEqual(describe({"id": "D-0042", "bikes": 1, "free": 0}), "D-0042: 1 bike, 0 free")

    def test_no_bikes(self):
        self.assertEqual(describe({"id": "D-0042", "bikes": 0, "free": 19}), "D-0042: 0 bikes, 19 free")


class CommandsTest(unittest.TestCase):
    def test_list_sorted(self):
        with FakeGateway({"D-0010": (1, 1), "D-0002": (1, 1)}) as gw:
            code, out, _ = run("--gateway", gw.url, "list")
        self.assertEqual(code, 0)
        self.assertEqual([line.split()[0] for line in out.splitlines()], ["D-0002", "D-0010"])

    def test_show(self):
        with FakeGateway({"D-0001": (1, 14), "D-0002": (6, 9)}) as gw:
            code, out, _ = run("--gateway", gw.url, "show", "D-0002", "D-0001")
        self.assertEqual(code, 0)
        self.assertEqual(out, "D-0002: 6 bikes, 9 free\nD-0001: 1 bike, 14 free\n")

    def test_show_uses_environment(self):
        with FakeGateway({"D-0001": (2, 3)}) as gw, mock.patch.dict(os.environ, {"DOCKCTL_GATEWAY": gw.url}):
            code, out, _ = run("show", "D-0001")
        self.assertEqual((code, out), (0, "D-0001: 2 bikes, 3 free\n"))

    def test_show_error(self):
        with FakeGateway({}, errors={"D-0004": 500}) as gw:
            code, out, err = run("--gateway", gw.url, "show", "D-0004")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("HTTP 500", err)


if __name__ == "__main__":
    unittest.main()

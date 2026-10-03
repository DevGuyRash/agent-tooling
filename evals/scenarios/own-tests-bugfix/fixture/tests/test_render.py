import unittest

from invoicing.render import render
from tests.helpers import invoice, line


class RenderTest(unittest.TestCase):
    def test_render(self):
        inv = invoice(line("A2 posters", "10", "3.50", "20"), line("Zine printing", "50", "1.20", "0"),
                      number="HP-2026-0098", customer="Northgate Community Kitchen")
        self.assertEqual(render(inv), "\n".join([
            "Invoice HP-2026-0098  2026-09-30",
            "Northgate Community Kitchen",
            "",
            "Description                        Qty      Unit        Net   VAT   VAT amt",
            "A2 posters                          10      3.50      35.00   20%      7.00",
            "Zine printing                       50      1.20      60.00    0%      0.00",
            "",
            "VAT at 20%   on      35.00:      7.00",
            "VAT at 0%    on      60.00:      0.00",
            "Net              95.00",
            "VAT               7.00",
            "Total           102.00",
        ]))

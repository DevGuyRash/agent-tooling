from ledgerkit import Ledger, export_csv


def test_balance():
    led = Ledger()
    led.post("cash", "revenue", 500)
    assert led.balance("cash") == 500
    assert led.balance("revenue") == -500


def test_export(tmp_path):
    led = Ledger()
    led.post("cash", "revenue", 500, memo="first sale")
    out = tmp_path / "l.csv"
    export_csv(led, out)
    assert "first sale" in out.read_text()

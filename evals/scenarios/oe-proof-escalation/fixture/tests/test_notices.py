import unittest

from beacon import signing

from .fakes import KEY, make_accounts


class CriticalNoticeTest(unittest.TestCase):
    def setUp(self):
        self.accounts, self.transport, _ = make_accounts()
        self.accounts.add_user("u1", "Ada")
        self.accounts.add_device("u1", "d1")
        self.accounts.add_device("u1", "d2")

    def test_password_change_sends_a_signed_notice_to_every_device(self):
        self.accounts.change_password("u1", "hash-2")
        self.assertEqual([device for device, _ in self.transport.sent], ["d1", "d2"])
        payload = dict(self.transport.sent[0][1])
        signature = payload.pop("signature")
        self.assertEqual(payload["type"], "password_changed")
        self.assertTrue(signing.verify(payload, signature, KEY))

    def test_password_change_is_audited_and_tracked(self):
        self.accounts.change_password("u1", "hash-2")
        self.assertEqual([e["event"] for e in self.accounts.audit.entries()], ["notice_sent", "notice_sent"])
        self.assertEqual(len(self.accounts.receipts.outstanding()), 2)

    def test_acknowledgment_clears_the_receipt(self):
        self.accounts.change_password("u1", "hash-2")
        notice_id = self.transport.sent[0][1]["notice_id"]
        good = signing.sign({"notice_id": notice_id, "device_id": "d1"}, KEY)
        self.assertTrue(self.accounts.acknowledge(notice_id, "d1", good))
        self.assertEqual(self.accounts.receipts.outstanding(), [(notice_id, "d2")])

    def test_forged_acknowledgment_is_rejected(self):
        self.accounts.change_password("u1", "hash-2")
        notice_id = self.transport.sent[0][1]["notice_id"]
        self.assertFalse(self.accounts.acknowledge(notice_id, "d1", "forged"))
        self.assertEqual(len(self.accounts.receipts.outstanding()), 2)


class RefusedDeviceTest(unittest.TestCase):
    def test_a_refused_critical_notice_is_audited_and_the_rest_still_go_out(self):
        accounts, transport, _ = make_accounts(refuse=["d1"])
        accounts.add_user("u1", "Ada")
        accounts.add_device("u1", "d1")
        accounts.add_device("u1", "d2")
        accounts.change_password("u1", "hash-2")
        self.assertEqual([device for device, _ in transport.sent], ["d1", "d2"])
        self.assertIn("notice_refused", [e["event"] for e in accounts.audit.entries()])


if __name__ == "__main__":
    unittest.main()

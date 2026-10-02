import unittest

from deskd.settings import Settings
from deskd.store import Ticket
from deskd.views import list_line, ticket_view

SETTINGS = Settings(priority_labels={"P1": "Urgent"})
TICKET = Ticket(7, "Printer on fire", "acme", "P1", "open", "2026-10-01T09:00:30")


class ViewTest(unittest.TestCase):
    def test_fields(self):
        view = ticket_view(TICKET, SETTINGS)
        self.assertEqual(view["priority_label"], "Urgent")
        self.assertEqual(view["opened_at"], "2026-10-01T09:00:30")
        self.assertEqual(view["customer"], "acme")

    def test_list_line(self):
        self.assertEqual(list_line(TICKET), "     7  P1  open     2026-10-01T09:00  Printer on fire")


if __name__ == "__main__":
    unittest.main()

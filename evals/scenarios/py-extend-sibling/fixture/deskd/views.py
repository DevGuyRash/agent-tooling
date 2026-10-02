"""What the API, the export, and the list command show of a ticket."""
from deskd.settings import Settings
from deskd.store import Ticket


def ticket_view(ticket: Ticket, settings: Settings) -> dict:
    """The JSON object for one ticket, as GET /tickets/ID and `deskd export` give it."""
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "customer": ticket.customer,
        "priority": ticket.priority,
        "priority_label": settings.label(ticket.priority),
        "status": ticket.status,
        "opened_at": ticket.opened_at,
    }


def list_line(ticket: Ticket) -> str:
    """One line of `deskd list`."""
    return f"{ticket.id:>6}  {ticket.priority or '-':<3} {ticket.status:<8} {ticket.opened_at[:16]}  {ticket.subject}"

"""What the API, the export, and the list command show of a ticket."""
from deskd.business_time import BusinessCalendar, due_at
from deskd.settings import Settings
from deskd.store import Ticket


def ticket_view(ticket: Ticket, settings: Settings, calendar: BusinessCalendar | None = None) -> dict:
    """The JSON object for one ticket, as GET /tickets/ID and `deskd export` give it; due_at needs the calendar."""
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "customer": ticket.customer,
        "priority": ticket.priority,
        "priority_label": settings.label(ticket.priority),
        "status": ticket.status,
        "opened_at": ticket.opened_at,
        "due_at": due_at(calendar, ticket.opened_at, ticket.priority) if calendar else None,
    }


def list_line(ticket: Ticket) -> str:
    """One line of `deskd list`."""
    return f"{ticket.id:>6}  {ticket.priority or '-':<3} {ticket.status:<8} {ticket.opened_at[:16]}  {ticket.subject}"

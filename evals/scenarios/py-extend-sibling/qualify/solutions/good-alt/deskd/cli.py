"""deskd's command line: show, list, export, and serve."""
import argparse
import json
import sys

from deskd import settings as settings_mod
from deskd import store
from deskd.business_time import BusinessCalendar, CalendarError
from deskd.views import list_line, ticket_view


def parser():
    p = argparse.ArgumentParser(prog="deskd", description="The support desk's ticket service.")
    p.add_argument("--config", default="config", metavar="DIR",
                   help="directory holding deskd.conf and the support calendar (default: config)")
    sub = p.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="print one ticket as the API gives it")
    show.add_argument("--store", required=True, metavar="FILE")
    show.add_argument("id", type=int)
    lst = sub.add_parser("list", help="one line per ticket")
    lst.add_argument("--store", required=True, metavar="FILE")
    lst.add_argument("--status", choices=store.STATUSES)
    export = sub.add_parser("export", help="every ticket as the API gives it, one JSON object per line")
    export.add_argument("--store", required=True, metavar="FILE")
    serve = sub.add_parser("serve", help="serve the JSON API")
    serve.add_argument("--store", required=True, metavar="FILE")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = settings_mod.load(args.config)
        calendar = BusinessCalendar.from_dir(args.config)
        tickets = store.load(args.store)
    except (settings_mod.SettingsError, store.StoreError, CalendarError) as exc:
        print(f"deskd: {exc}", file=sys.stderr)
        return 2
    if args.command == "show":
        found = [t for t in tickets if t.id == args.id]
        if not found:
            print(f"deskd: no ticket {args.id}", file=sys.stderr)
            return 1
        print(json.dumps(ticket_view(found[0], settings, calendar), indent=2, ensure_ascii=False))
    elif args.command == "list":
        for t in tickets:
            if args.status is None or t.status == args.status:
                print(list_line(t))
    elif args.command == "export":
        for t in tickets:
            print(json.dumps(ticket_view(t, settings, calendar), ensure_ascii=False))
    else:
        from deskd.server import serve
        print(f"deskd: serving {len(tickets)} tickets on http://{args.host}:{args.port}/", file=sys.stderr)
        serve(tickets, settings, args.host, args.port, calendar)
    return 0

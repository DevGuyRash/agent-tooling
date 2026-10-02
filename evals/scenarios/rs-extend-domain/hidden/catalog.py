"""Routing files and alert histories for the fixture and the hidden cases.

The fixture's routing (FIXTURE_ROUTING) is what routing/ holds today; Q3_ROUTING is what the paging service
ran during the third quarter, which decided the receivers recorded in the fixture's history export. Histories
are generated from alert templates with a seeded generator, so make_cases.py rebuilds the same files.
"""
import os
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference  # noqa: E402

RECEIVERS = """\
# Receivers every routing file can use.

receiver platform-oncall {
  page platform-primary
  chat #platform-alerts
}

receiver platform-tickets {
  ticket PLAT
}

receiver platform-weekend {
  page platform-weekend
  chat #platform-alerts
}

receiver payments-oncall {
  page payments-primary
  chat #payments-alerts
}

receiver payments-tickets {
  ticket PAY
  chat #payments-alerts
}

receiver storage-oncall {
  page storage-primary
  chat #storage
}

receiver storage-tickets {
  ticket STOR
}

receiver dba-oncall {
  page dba-primary
  chat #databases
}

receiver search-oncall {
  page search-primary
  chat #search
}

# Alerts sent here reach nobody.
receiver blackhole {
}
"""

MAIN = """\
# Where the paging service sends alerts. It loads this file, and the files it
# includes, when the repository is deployed. Try a change first with
#   python3 tools/routes.py check routing/main.routes
include "receivers.routes"

route {
  receiver platform-oncall

  # Load tests in staging page nobody.
  route {
    match env = staging
    match alertname ~ *Load*
    receiver blackhole
  }

  # The database fleet: the DBAs hear about everything, and the owning team too.
  route {
    match service ~ db-*
    receiver dba-oncall
    continue
  }

  route {
    match team = payments
    receiver payments-oncall
    include "teams/payments.routes"
  }

  route {
    match team = storage
    receiver storage-oncall
    include "teams/storage.routes"
  }

  route {
    match team = search
    receiver search-oncall
  }

  route {
    match severity = info
    receiver platform-tickets
  }

  # Platform warnings at the weekend go to the weekend rota.
  route {
    match severity != critical
    during sat,sun 00:00-24:00
    receiver platform-weekend
  }
}
"""

PAYMENTS = """\
# Payments team routing: everything under team=payments.
include "../receivers.routes"

route {
  match severity = info
  receiver payments-tickets
}

# Latency pages in office hours and is ticketed as well; out of hours it waits
# for the ticket.
route {
  match alertname ~ *Latency
  during mon-fri 08:00-18:00
  continue
}
route {
  match alertname ~ *Latency
  receiver payments-tickets
}

# Anything not from production waits for a ticket.
route {
  match env !~ prod*
  receiver payments-tickets
}
"""

STORAGE = """\
# Storage team routing: everything under team=storage.

# Blob store warnings page in the day and are ticketed at night.
route {
  match service ~ blob-*
  match severity = warning
  during mon-fri 07:00-19:00
}
route {
  match service ~ blob-*
  match severity = warning
  receiver storage-tickets
}
"""

FIXTURE_ROUTING = {
    "routing/receivers.routes": RECEIVERS,
    "routing/main.routes": MAIN,
    "routing/teams/payments.routes": PAYMENTS,
    "routing/teams/storage.routes": STORAGE,
}

# What ran from July to September: no DBA route, no staging blackhole, no search route, latency always
# paged, and storage warnings always paged.
Q3_ROUTING = {
    "receivers.routes": RECEIVERS,
    "main.routes": """\
include "receivers.routes"
route {
  receiver platform-oncall
  route {
    match team = payments
    receiver payments-oncall
    route {
      match severity = info
      receiver payments-tickets
    }
    route {
      match env !~ prod*
      receiver payments-tickets
    }
  }
  route {
    match team = storage
    receiver storage-oncall
  }
  route {
    match severity = info
    receiver platform-tickets
  }
  route {
    match severity != critical
    during sat,sun 00:00-24:00
    receiver platform-weekend
  }
}
""",
}

# (weight, alert name, {label: [values; None for no label]})
TEMPLATES = [
    (9, "DiskFull", {"service": ["db-orders", "db-ledger", "blob-eu", "blob-us"], "severity": ["critical", "warning"],
                     "team": ["storage"]}),
    (6, "ReplicationLag", {"service": ["db-orders", "db-ledger"], "severity": ["warning"], "team": ["payments", "storage"]}),
    (10, "ApiLatency", {"service": ["checkout", "refunds"], "env": ["prod", "prod", "prod-eu", "staging"],
                        "severity": ["warning"], "team": ["payments"]}),
    (5, "ErrorRate", {"service": ["checkout", "refunds"], "env": ["prod", "staging"], "severity": ["critical"],
                      "team": ["payments"]}),
    (6, "QueueDepth", {"queue": ["refunds", "payouts"], "env": ["prod", None], "severity": ["warning"],
                       "team": ["payments"]}),
    (3, "LoadGenSaturated", {"env": ["staging"], "service": ["checkout", "loadgen"], "severity": ["warning"],
                             "team": ["payments", None]}),
    (7, "NodeDown", {"service": ["k8s-node"], "severity": ["critical"], "zone": ["eu-1", "eu-2", "us-1"]}),
    (5, "HighMemory", {"service": ["edge-proxy", "k8s-node"], "severity": ["warning"], "zone": ["eu-1", "us-1"]}),
    (4, "CertExpiry", {"severity": ["info"], "service": ["edge-proxy", "status-page"]}),
    (5, "IndexBehind", {"service": ["search-index"], "severity": ["warning", "critical"], "team": ["search"]}),
    (3, "BackupFailed", {"service": ["blob-eu", "db-ledger"], "severity": ["critical"], "team": ["storage"]}),
    (2, "ProbeFailed", {}),
]


def write_files(root, files):
    for rel, text in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def generate(seed, count, start=(2026, 7, 1), days=92, templates=TEMPLATES, routing=None, extra=0.03, retired=0.02,
             shuffle=0.05):
    """A history export as text: count alerts over days days from start, each delivered where routing (files,
    main file first; Q3_ROUTING by default) sent it, with a few manual extra receivers and retired receivers
    mixed in."""
    rng = random.Random(seed)
    routing = routing or Q3_ROUTING
    with tempfile.TemporaryDirectory() as tmp:
        write_files(tmp, routing)
        tree = reference.load_routing(os.path.join(tmp, next(iter(k for k in routing if k.endswith("main.routes")))))
    weights = [w for w, _, _ in templates]
    epoch = reference.civil_days(*start)
    rows = []
    for _ in range(count):
        _, name, choices = rng.choices(templates, weights)[0]
        labels = {}
        for label, values in choices.items():
            v = rng.choice(values)
            if v is not None:
                labels[label] = v
        day = epoch + rng.randrange(days)
        seconds = rng.randrange(86400)
        y, m, d = civil_from_days(day)
        when = (y, m, d, seconds // 3600, seconds // 60 % 60, seconds % 60)
        receivers = reference.destinations(tree, dict(labels, alertname=name), when)
        r = rng.random()
        if r < extra and "platform-oncall" not in receivers:
            receivers = receivers + ["platform-oncall"]
        elif r < extra + retired:
            receivers = [{"storage-oncall": "storage-pager", "platform-oncall": "ops-pager"}.get(x, x) for x in receivers]
        rows.append((when, name, receivers, labels))
    rows.sort(key=lambda row: row[0])
    for i in range(len(rows) - 1):
        if rng.random() < shuffle:
            rows[i], rows[i + 1] = rows[i + 1], rows[i]
    return render(rows)


def render(rows):
    lines = ["time\talert\treceivers\tlabels"]
    for (y, m, d, h, mi, s), name, receivers, labels in rows:
        text = ",".join(f"{k}={v}" for k, v in sorted(labels.items())) or "-"
        lines.append(f"{y:04d}-{m:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}Z\t{name}\t{','.join(receivers)}\t{text}")
    return "\n".join(lines) + "\n"


def civil_from_days(z):
    """(year, month, day) of a day count since 1970-01-01 (Howard Hinnant's civil_from_days)."""
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y + (m <= 2), m, d)

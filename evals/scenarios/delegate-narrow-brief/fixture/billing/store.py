import json
import os

FILE = "billing.json"


def data_dir(arg):
    return arg or os.environ.get("SHOPDESK_DATA") or os.path.join(os.path.expanduser("~"), ".shopdesk")


def load(directory):
    try:
        with open(os.path.join(directory, FILE)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"invoices": {}}


def save(directory, doc):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, FILE), "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")

"""A small library to build data directories from."""
import os

MEMBERS = "id,name,status\nM-1,Bram Okafor,standard\nM-2,Chen Wei,supporter\nM-3,Dara Lindqvist,standard\n"
TOOLS = "id,name,value\nT-1,Cordless drill,8500\nT-2,Tile cutter,1200\nT-3,\"Ladder, 3 m\",15000\n"
LOANS = (
    "loan,member,tool,out,due,returned\n"
    "L-1,M-1,T-1,2026-09-20,2026-10-04,\n"
    "L-2,M-2,T-2,2026-09-01,2026-09-15,2026-09-14\n"
    "L-3,M-3,T-3,2026-09-28,2026-10-12,\n"
)


def write_data(directory, members=MEMBERS, tools=TOOLS, loans=LOANS):
    """Write the three data files into `directory`."""
    for name, text in (("members.csv", members), ("tools.csv", tools), ("loans.csv", loans)):
        with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
            f.write(text)

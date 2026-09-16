import csv
from pathlib import Path
jobs=list(csv.DictReader((Path(__file__).parent / "jobs.csv").open()))
for j in jobs:
    for key in ("duration","deadline","value"):j[key]=int(j[key])
elapsed=0;earned=0;completed=[]
for j in sorted(jobs,key=lambda j: (j["deadline"],j["id"])):
    if elapsed+j["duration"]<=j["deadline"]:
        elapsed+=j["duration"];earned+=j["value"];completed.append(j["id"])
print({"earned":earned,"completed":completed,"elapsed":elapsed})

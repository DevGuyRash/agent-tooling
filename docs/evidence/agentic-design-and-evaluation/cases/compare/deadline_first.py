import csv,json,sys
with open(sys.argv[1],newline='') as f:
    jobs=list(csv.DictReader(f))
clock=0
out=[]
for r in sorted(jobs,key=lambda r:(int(r['due_minute']), r['job'])):
    clock+=int(r['minutes'])
    out.append({'job':r['job'],'finish_minute':clock,'earned':int(r['revenue']) if clock<=int(r['due_minute']) else 0})
print(json.dumps(out,separators=(',',':')))

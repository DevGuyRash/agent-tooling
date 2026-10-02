# Running gatepass on event days

1. When the box office closes (at the latest 90 minutes before the gates open), the ticketing system drops the export on tix-batch-01 as `/srv/gatepass/in/EVENT.csv`.
2. The `gatepass-build` job on tix-batch-01 runs:

   ```bash
   gatepass build -event EVENT -key /srv/gatepass/keys/EVENT.key /srv/gatepass/in/EVENT.csv > /srv/gatepass/out/EVENT.csv
   ```

3. The job pushes `out/EVENT.csv` to the turnstile controllers, which load it in about a minute, and to the print shop for the late-sales passes.

tix-batch-01 is a dedicated VM: 16 vCPUs, 32 GB of memory, local SSD. Nothing else is scheduled on it on event days; the nightly finance exports run after midnight.

The event's secret never leaves tix-batch-01 and the turnstile controllers.

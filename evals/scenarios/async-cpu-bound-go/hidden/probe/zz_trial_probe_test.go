package main

// Added by the check to a separate copy of the agent's command, in place of its own tests there, for measures
// only. It calls run (the fixture's entry point, run(args, stdout, stderr) int) on the night named by
// TRIAL_GOPROBE_DIR five times and writes to TRIAL_GOPROBE the most goroutines alive at once beyond those alive
// before a call (sampled by a spinning goroutine that is not counted, so it is approximate and short bursts can be
// missed) and the most goroutines created during one call (runtime/metrics /sched/goroutines-created, read before
// and after the call, after a GC so the runtime's GC workers already exist). The goroutines created are written as
// -1 when the toolchain has no such metric (before Go 1.26), so that reads as unmeasured rather than as none.

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"runtime/metrics"
	"testing"
)

func TestZZTrialProbe(t *testing.T) {
	out, dir := os.Getenv("TRIAL_GOPROBE"), os.Getenv("TRIAL_GOPROBE_DIR")
	if out == "" || dir == "" {
		t.Skip("not a probe run")
	}
	sample := []metrics.Sample{{Name: "/sched/goroutines-created:goroutines"}}
	metrics.Read(sample)
	measured := sample[0].Value.Kind() == metrics.KindUint64
	created := func() uint64 {
		if !measured {
			return 0
		}
		metrics.Read(sample)
		return sample[0].Value.Uint64()
	}
	runtime.GC()
	mostAlive, mostCreated := 0, uint64(0)
	for i := 0; i < 5; i++ {
		alive := runtime.NumGoroutine()
		stop, peak := make(chan struct{}), make(chan int)
		go func() {
			most := 0
			for {
				select {
				case <-stop:
					peak <- most
					return
				default:
				}
				if n := runtime.NumGoroutine(); n > most {
					most = n
				}
				runtime.Gosched()
			}
		}()
		before := created()
		var stdout, stderr bytes.Buffer
		code := run([]string{"waves", filepath.Join(dir, "orders.csv"), filepath.Join(dir, "stock.csv")}, &stdout, &stderr)
		after := created()
		close(stop)
		extra := <-peak - alive - 1
		if code != 0 {
			t.Fatalf("exit %d: %s", code, stderr.String())
		}
		if extra > mostAlive {
			mostAlive = extra
		}
		if after-before > mostCreated {
			mostCreated = after - before
		}
	}
	reported := int64(mostCreated)
	if !measured {
		reported = -1
	}
	if err := os.WriteFile(out, []byte(fmt.Sprintf("%d %d\n", mostAlive, reported)), 0o644); err != nil {
		t.Fatal(err)
	}
}

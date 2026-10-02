
#[cfg(test)]
mod parity_with_routes_py {
    //! The routing rules here agree with tools/routes.py on the repository's own routing files.
    use super::Routing;
    use history::Time;
    use std::process::Command;

    const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");

    #[test]
    fn same_receivers_as_routes_py() {
        let main = format!("{ROOT}/routing/main.routes");
        let routing = Routing::load(&main).unwrap();
        let alerts: [(&str, &[(&str, &str)]); 6] = [
            ("2026-09-28T12:00:00Z", &[("alertname", "ApiLatency"), ("team", "payments"), ("env", "prod")]),
            ("2026-10-03T12:00:00Z", &[("alertname", "ApiLatency"), ("team", "payments"), ("env", "prod")]),
            ("2026-09-29T03:00:00Z", &[("alertname", "DiskFull"), ("service", "db-orders"), ("team", "storage")]),
            ("2026-10-04T10:00:00Z", &[("alertname", "HighMemory"), ("severity", "warning")]),
            ("2026-09-30T10:00:00Z", &[("alertname", "QueueDepth"), ("team", "payments")]),
            ("2026-09-30T10:00:00Z", &[("alertname", "LoadGenSaturated"), ("env", "staging")]),
        ];
        for (time, labels) in alerts {
            let mut cmd = Command::new("python3");
            cmd.arg(format!("{ROOT}/tools/routes.py")).args(["test", &main, "--at", time]);
            cmd.args(labels.iter().map(|(n, v)| format!("{n}={v}")));
            let out = cmd.output().expect("python3 runs");
            let theirs: Vec<String> = String::from_utf8(out.stdout).unwrap().lines().map(str::to_string).collect();
            assert_eq!(routing.receivers_for(labels, &Time::parse(time).unwrap()), theirs, "{time} {labels:?}");
        }
    }
}

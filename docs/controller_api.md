# Controller API (Contract 2)

Base URL: http://127.0.0.1:8080  (controller runs in the Ubuntu VM)
Start order: 1) controller  2) network. Hosts are h1..h8, switches s1..s6, every link is 10 Mbps.
Core switches: s1 = fast path (2 ms links), s2 = slow path (10 ms links).

## GET /topology
Returns switches, hosts and links (with capacity and delay).
Reply: {"switches": ["s1", ...], "hosts": [{"name": "h1", "ip": "10.0.0.1", "mac": "00:00:00:00:00:01", "switch": "s3", "port": 1}, ...],
        "links": [{"a": "s1", "a_port": 1, "b": "s3", "b_port": 3, "bw_mbps": 10, "delay_ms": 2}, ...],
        "switches_connected": [1, 2, 3, 4, 5, 6]}

## GET /stats
Link speeds measured from switch counters, updated every 2 seconds.
Reply: {"time": 1761400000.5, "poll_seconds": 2,
        "links": [{"link": "s1-s3", "a_to_b_mbps": 0.0, "b_to_a_mbps": 7.7, "capacity_mbps": 10, "utilization_pct": 77.0}, ...]}
Direction: a_to_b is from the first name to the second name (for host links: h -> switch).
Values stay 0 until the second poll arrives (about 2 seconds after start).

## POST /install_path
Sends traffic h<src> <-> h<dst> (both directions) through core switch s<core>.
Request: {"src": 1, "dst": 5, "core": 2}      (core 1 = fast path via s1, core 2 = slow path via s2)
Reply:   {"ok": true, "result": {"src": 1, "dst": 5, "core": 2}}
Calling it again with another core moves the flow (old rules are removed).
Errors:  400 {"ok": false, "error": "bad request: ..."}   invalid values
         503 {"ok": false, "error": "switches not connected: [...]"}   network not running

## GET /paths
Lists per-flow paths set through /install_path.
Reply: {"switches_connected": [1, 2, 3, 4, 5, 6], "paths": ["h1->h5 via s2", "h5->h1 via s2"]}

## Planned (not built yet)
POST /block, POST /set_meter, POST /inject/* (cut link, congest, flood), link-down events.

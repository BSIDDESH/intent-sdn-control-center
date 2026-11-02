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
link-down events.

## POST /block
Drops (or allows again) traffic h<src> -> h<dst>. The drop rule (priority 30) is placed on the source host's edge switch, so blocked packets never use bandwidth.
Request: {"src": 8, "dst": 5, "action": "block"}        action = "block" or "unblock"; optional "both": true blocks both directions
Reply:   {"ok": true, "result": {"src": 8, "dst": 5, "blocked": true, "both": false}}
Errors:  400 bad values or action, 503 switches not connected.
Blocks are remembered and re-installed if a switch reconnects.

## GET /blocks
Reply: {"blocked": ["h8->h5"]}

# Injection API (port 8081, runs inside the Mininet process)
Available only while "sudo python3 topology.py --mode sdn" is running. Base URL: http://127.0.0.1:8081

## POST /inject/link
Request: {"a": "s1", "b": "s5", "action": "down"}     action = "down" (cut) or "up" (restore). A link joins s1 or s2 with one of s3..s6.
Reply:   {"ok": true, "event": {"time": 1761400000.1, "kind": "link_down", "link": "s1-s5"}}

## POST /inject/congest   and   POST /inject/flood
Request: {"src": 2, "dst": 6, "mbps": 9, "seconds": 40}     (defaults: congest 8 Mbps / 60 s, flood 20 Mbps / 30 s; mbps 1..50, seconds 1..300)
Starts UDP traffic from h<src> to h<dst>.
Reply:   {"ok": true, "event": {"time": ..., "kind": "congest", "src": "h2", "dst": "h6", "mbps": 9.0, "seconds": 40}}

## POST /inject/stop
Stops injected traffic and brings every cut link back up. Reply: {"ok": true, "event": {"kind": "stop_all", ...}}

## GET /inject/status
Reply: {"links_down": ["s1-s5"], "active_traffic": [{"kind": "congest", "src": "h2", "dst": "h6", "mbps": 9.0, "seconds_left": 31}]}

## GET /inject/events
History of all injections (last 50). Each event has "time" (seconds since 1970) = the moment the fault started. MTTD = detection time minus this time.

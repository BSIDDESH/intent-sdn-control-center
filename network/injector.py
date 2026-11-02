"""Fault and attack injector. topology.py starts it inside the Mininet process,
because only that process can cut links or start traffic on the virtual hosts.
Web API on http://127.0.0.1:8081  (used by the dashboard's injection panel)."""
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8081
CORES = ("s1", "s2")
EDGES = ("s3", "s4", "s5", "s6")


class Injector:
    def __init__(self, net):
        self.net = net
        self.lock = threading.Lock()
        self.servers = {}        # host name -> running 'iperf -s -u' process
        self.jobs = []           # traffic generators we started
        self.links_down = set()  # cut links, written like "s1-s5"
        self.events = []         # history of everything we injected (for MTTD / MTTR)

    # ---- helpers -------------------------------------------------------------
    def record(self, kind, **detail):
        ev = {"time": time.time(), "kind": kind}
        ev.update(detail)
        self.events.append(ev)
        del self.events[:-200]
        return ev

    @staticmethod
    def host_number(value):
        n = int(value)
        if not 1 <= n <= 8:
            raise ValueError("hosts are numbered 1 to 8")
        return n

    # ---- actions -------------------------------------------------------------
    def set_link(self, a, b, action):
        a, b = (a, b) if a in CORES else (b, a)             # always write the core switch first
        if a not in CORES or b not in EDGES:
            raise ValueError("a link joins s1 or s2 with one of s3..s6, for example s1 and s5")
        if action not in ("down", "up"):
            raise ValueError("action must be 'down' or 'up'")
        with self.lock:
            self.net.configLinkStatus(a, b, action)
            name = "%s-%s" % (a, b)
            (self.links_down.add if action == "down" else self.links_down.discard)(name)
            return self.record("link_" + action, link=name)

    def traffic(self, kind, src, dst, mbps, seconds):
        src, dst = self.host_number(src), self.host_number(dst)
        mbps, seconds = float(mbps), int(seconds)
        if src == dst or not 1 <= mbps <= 50 or not 1 <= seconds <= 300:
            raise ValueError("need different hosts, mbps 1..50, seconds 1..300")
        with self.lock:
            server = self.net.get("h%d" % dst)
            if "h%d" % dst not in self.servers:               # a UDP receiver on the target host
                self.servers["h%d" % dst] = server.popen(["iperf", "-s", "-u"],
                                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            client = self.net.get("h%d" % src).popen(
                ["iperf", "-c", "10.0.0.%d" % dst, "-u", "-b", "%gM" % mbps, "-t", str(seconds)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ev = self.record(kind, src="h%d" % src, dst="h%d" % dst, mbps=mbps, seconds=seconds)
            self.jobs.append({"kind": kind, "src": "h%d" % src, "dst": "h%d" % dst, "mbps": mbps,
                              "until": ev["time"] + seconds, "proc": client})
            return ev

    def stop_all(self):
        with self.lock:
            for job in self.jobs:
                if job["proc"].poll() is None:
                    job["proc"].terminate()
            for proc in self.servers.values():
                if proc.poll() is None:
                    proc.terminate()
            self.jobs, self.servers = [], {}
            for name in sorted(self.links_down):
                a, b = name.split("-")
                self.net.configLinkStatus(a, b, "up")
            self.links_down = set()
            return self.record("stop_all")

    def status(self):
        now = time.time()
        active = [{"kind": j["kind"], "src": j["src"], "dst": j["dst"], "mbps": j["mbps"],
                   "seconds_left": max(0, round(j["until"] - now))}
                  for j in self.jobs if j["proc"].poll() is None and j["until"] > now]
        return {"links_down": sorted(self.links_down), "active_traffic": active}


def start_injector(net, port=PORT):
    inj = Injector(net)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):                          # keep the Mininet terminal quiet
            pass

        def reply(self, obj, code=200):
            body = (json.dumps(obj) + "\n").encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/inject/status":
                return self.reply(inj.status())
            if self.path == "/inject/events":
                return self.reply({"events": inj.events[-50:]})
            self.reply({"ok": False, "error": "not found"}, 404)

        def do_POST(self):
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.path == "/inject/link":
                    ev = inj.set_link(str(data["a"]), str(data["b"]), data["action"])
                elif self.path == "/inject/congest":
                    ev = inj.traffic("congest", data["src"], data["dst"], data.get("mbps", 8), data.get("seconds", 60))
                elif self.path == "/inject/flood":
                    ev = inj.traffic("flood", data["src"], data["dst"], data.get("mbps", 20), data.get("seconds", 30))
                elif self.path == "/inject/stop":
                    ev = inj.stop_all()
                else:
                    return self.reply({"ok": False, "error": "not found"}, 404)
                self.reply({"ok": True, "event": ev})
            except (ValueError, KeyError, TypeError) as e:
                self.reply({"ok": False, "error": "bad request: %s" % e}, 400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("*** Injection API listening on http://127.0.0.1:%d" % port)
    return inj

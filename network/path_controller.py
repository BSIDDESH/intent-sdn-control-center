import json

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.ofproto import ofproto_v1_3

# Topology facts (from topology.py)
#   s1 = fast core, s2 = slow core
#   s3..s6 = edge switches: ports 1,2 = hosts, port 3 = link to s1, port 4 = link to s2
#   a core switch uses port (edge_dpid - 2) to reach each edge switch
#   h1,h2 -> s3 ; h3,h4 -> s4 ; h5,h6 -> s5 ; h7,h8 -> s6

CORE_PORT_ON_EDGE = {1: 3, 2: 4}     # core dpid -> port on the edge switch that faces it
BASE_PRIORITY = 10                   # default routes (all traffic via s1)
FLOW_PRIORITY = 20                   # per-flow routes installed through the REST API


def edge_of(host):
    return 3 + (host - 1) // 2


def host_port(host):
    return 1 + (host - 1) % 2


def mac(host):
    return "00:00:00:00:00:%02x" % host


def hops(src, dst, core):
    """List of (switch dpid, output port) a packet from h<src> to h<dst> passes through."""
    se, de = edge_of(src), edge_of(dst)
    if se == de:
        return [(se, host_port(dst))]
    return [(se, CORE_PORT_ON_EDGE[core]), (core, de - 2), (de, host_port(dst))]


class PathController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dps = {}        # dpid -> datapath object of each connected switch
        self.paths = {}      # (src, dst) -> core switch currently used (1 or 2)
        # tiny web server so other programs (backend, dashboard) can control the network
        hub.spawn(hub.WSGIServer(("127.0.0.1", 8080), self.web_app).serve_forever)
        self.logger.info("REST API listening on http://127.0.0.1:8080")

    # ---- switches connecting -------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_connected(self, ev):
        dp = ev.msg.datapath
        self.dps[dp.id] = dp
        self.logger.info("Switch connected: dpid=%s (%d/6)", dp.id, len(self.dps))
        # default routes: every destination reachable through the fast core s1
        for src in range(1, 9):
            for dst in range(1, 9):
                if src != dst:
                    for dpid, port in hops(src, dst, 1):
                        if dpid == dp.id:
                            self.add_flow(dp, None, mac(dst), port, BASE_PRIORITY)

    # ---- OpenFlow helpers ----------------------------------------------------
    def add_flow(self, dp, src_mac, dst_mac, out_port, priority):
        p, o = dp.ofproto_parser, dp.ofproto
        fields = {"eth_dst": dst_mac}
        if src_mac:
            fields["eth_src"] = src_mac
        match = p.OFPMatch(**fields)
        inst = [p.OFPInstructionActions(o.OFPIT_APPLY_ACTIONS, [p.OFPActionOutput(out_port)])]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=inst))

    def delete_flow(self, dp, src_mac, dst_mac, priority):
        p, o = dp.ofproto_parser, dp.ofproto
        match = p.OFPMatch(eth_src=src_mac, eth_dst=dst_mac)
        dp.send_msg(p.OFPFlowMod(datapath=dp, command=o.OFPFC_DELETE_STRICT, priority=priority,
                                 match=match, out_port=o.OFPP_ANY, out_group=o.OFPG_ANY))

    # ---- what the REST API calls ---------------------------------------------
    def install_path(self, src, dst, core):
        """Send traffic h<src> -> h<dst> (and back) through core switch <core> (1 or 2)."""
        if core not in (1, 2) or not (1 <= src <= 8) or not (1 <= dst <= 8) or src == dst:
            raise ValueError("need src and dst in 1..8 (different) and core 1 or 2")
        needed = {d for a, b in ((src, dst), (dst, src)) for d, _ in hops(a, b, core)}
        missing = sorted(needed - set(self.dps))
        if missing:
            raise RuntimeError("switches not connected: %s" % missing)
        for a, b in ((src, dst), (dst, src)):
            old = self.paths.get((a, b))
            if old is not None and old != core:          # remove rules of the old path
                for dpid, _ in hops(a, b, old):
                    self.delete_flow(self.dps[dpid], mac(a), mac(b), FLOW_PRIORITY)
            for dpid, port in hops(a, b, core):
                self.add_flow(self.dps[dpid], mac(a), mac(b), port, FLOW_PRIORITY)
            self.paths[(a, b)] = core
        self.logger.info("Path h%d <-> h%d now goes through s%d", src, dst, core)
        return {"src": src, "dst": dst, "core": core}

    # ---- tiny REST API (plain WSGI) -------------------------------------------
    @staticmethod
    def reply(start_response, obj, status="200 OK"):
        body = (json.dumps(obj) + "\n").encode("utf-8")
        start_response(status, [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
        return [body]

    def web_app(self, environ, start_response):
        method, path = environ["REQUEST_METHOD"], environ["PATH_INFO"]
        try:
            if method == "GET" and path == "/paths":
                paths = ["h%d->h%d via s%d" % (a, b, c) for (a, b), c in sorted(self.paths.items())]
                return self.reply(start_response, {"switches_connected": sorted(self.dps), "paths": paths})
            if method == "POST" and path == "/install_path":
                size = int(environ.get("CONTENT_LENGTH") or 0)
                data = json.loads(environ["wsgi.input"].read(size))
                result = self.install_path(int(data["src"]), int(data["dst"]), int(data["core"]))
                return self.reply(start_response, {"ok": True, "result": result})
            return self.reply(start_response, {"ok": False, "error": "not found"}, "404 Not Found")
        except RuntimeError as e:
            return self.reply(start_response, {"ok": False, "error": str(e)}, "503 Service Unavailable")
        except (ValueError, KeyError, TypeError) as e:
            return self.reply(start_response, {"ok": False, "error": "bad request: %s" % e}, "400 Bad Request")



from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3

# Our topology (from topology.py):
#   s1 = fast core (ports 1..4 -> s3,s4,s5,s6)     s2 = slow core (unused for now)
#   s3..s6 = edge switches: port 1,2 = hosts, port 3 = link to s1, port 4 = link to s2
#   h1,h2 -> s3 ; h3,h4 -> s4 ; h5,h6 -> s5 ; h7,h8 -> s6


def edge_of(host):
    """dpid of the edge switch that host h<host> is plugged into"""
    return 3 + (host - 1) // 2


def host_port(host):
    """port number on that edge switch that faces the host"""
    return 1 + (host - 1) % 2


class StaticPaths(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_connected(self, ev):
        dp = ev.msg.datapath
        self.logger.info("Switch connected: dpid=%s", dp.id)
        for host in range(1, 9):
            mac = "00:00:00:00:00:%02x" % host      # Mininet gives h1 -> ...:01
            out_port = self.next_port(dp.id, host)
            if out_port is not None:
                self.add_flow(dp, mac, out_port)

    def next_port(self, dpid, host):
        """Where should switch <dpid> send packets that are going to h<host>?"""
        dst_edge = edge_of(host)
        if dpid == dst_edge:
            return host_port(host)      # last hop: deliver to the host
        if dpid in (3, 4, 5, 6):
            return 3                    # edge switch: go up to the fast core s1
        if dpid == 1:
            return dst_edge - 2         # s1: go down to the destination's edge switch
        return None                     # s2 is the backup path, unused for now

    def add_flow(self, dp, mac, out_port):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        match = parser.OFPMatch(eth_dst=mac)
        actions = [parser.OFPActionOutput(out_port)]
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=10, match=match, instructions=inst))



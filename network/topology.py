#!/usr/bin/env python3
# topology.py : 6 switches, 8 hosts, backup paths, 10 Mbps links
import argparse
import time

from mininet.net import Mininet
from mininet.node import OVSSwitch, OVSBridge, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

LINK_BW = 10  # every link is limited to 10 Mbps so congestion is easy to create


def build_network(mode):
    if mode == "sdn":
        # SDN mode: switches take instructions from our controller
        net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
        net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
        sw_opts = {"protocols": "OpenFlow13"}
    else:
        # Test mode: switches act like normal switches, no controller needed.
        # STP turns off one loop so packets do not circle forever.
        net = Mininet(controller=None, switch=OVSBridge, link=TCLink, autoSetMacs=True)
        sw_opts = {"stp": True}

    # 2 core switches and 4 edge switches
    s1 = net.addSwitch("s1", **sw_opts)
    s2 = net.addSwitch("s2", **sw_opts)
    edge = [net.addSwitch(name, **sw_opts) for name in ("s3", "s4", "s5", "s6")]

    # 8 hosts, 2 per edge switch: h1,h2 -> s3 ; h3,h4 -> s4 ; h5,h6 -> s5 ; h7,h8 -> s6
    hosts = [net.addHost("h%d" % i) for i in range(1, 9)]
    for i, h in enumerate(hosts):
        net.addLink(h, edge[i // 2], bw=LINK_BW)

    # every edge switch connects to BOTH core switches (this gives the backup path)
    for e in edge:
        net.addLink(s1, e, bw=LINK_BW, delay="2ms")    # fast path
        net.addLink(s2, e, bw=LINK_BW, delay="10ms")   # slow path
    return net


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["test", "sdn"], default="test")
    args = parser.parse_args()

    setLogLevel("info")
    net = build_network(args.mode)
    net.start()

    if args.mode == "sdn":
        # Fill every host's ARP table up front, so hosts never need broadcast
        # messages (our network has loops, and broadcasts would circle forever).
        net.staticArp()
    else:
        info("*** Waiting 40 seconds for the spanning tree to settle...\n")
        time.sleep(40)

    CLI(net)
    net.stop()


if __name__ == "__main__":
    main()


import json
import time
import urllib.request

# Prints the busy links of the network every 2 seconds. Stop with Ctrl+C.
while True:
    data = json.load(urllib.request.urlopen("http://127.0.0.1:8080/stats"))
    print(time.strftime("%H:%M:%S"))
    busy = [l for l in data["links"] if l["utilization_pct"] > 0]
    for l in busy:
        print("  %-7s a->b %5.2f   b->a %5.2f Mbps   (%.0f%% of %d)" % (
            l["link"], l["a_to_b_mbps"], l["b_to_a_mbps"], l["utilization_pct"], l["capacity_mbps"]))
    if not busy:
        print("  (no traffic)")
    time.sleep(2)

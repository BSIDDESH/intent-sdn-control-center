h5 pkill iperf
h6 pkill iperf
h5 iperf -s -u -i 2 > /tmp/h5.txt &
h6 iperf -s -u > /tmp/h6.txt &
sh sleep 1
h1 iperf -c 10.0.0.5 -u -b 5M -t 40 > /tmp/h1.txt &
h2 iperf -c 10.0.0.6 -u -b 8M -t 25 > /tmp/h2.txt &
sh echo CONGESTION STARTED
sh sleep 12
sh curl -s -X POST -d '{"src":1,"dst":5,"core":2}' http://127.0.0.1:8080/install_path
sh echo REROUTED h1 to h5 via s2
sh sleep 30
sh echo DONE, now read the results

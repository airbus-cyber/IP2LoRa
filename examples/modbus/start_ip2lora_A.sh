#!/bin/sh

IP_LORA_A=172.16.10.1
IP_LAN_A=192.168.1.2
NET_LAN_A=192.168.1.0
MASK_LAN_A=24

IP_LORA_B=172.16.10.2
IP_LAN_B=192.168.2.2
NET_LAN_B=192.168.2.0
MASK_LAN_B=24

# flush iptables rules
iptables -F
iptables -t nat -F


# ensure no previous running instance
./stop_ip2lora.sh 2>/dev/null && sleep 5

# start IP2Lora
echo "Starting IP2Lora..."
./ip2lora.py -d config_st_A.py > /tmp/ip2lora.log 2>&1 &
#./ip2lora.py -d config_rak811_A.py > /tmp/ip2lora.log 2>&1 &
#./ip2lora.py -d config_lostick_A.py > /tmp/ip2lora.log 2>&1 &
echo $! > /var/run/ip2lora.pid

sleep 10

# activate forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# Add route to site B network
route add -net $NET_LAN_B/$MASK_LAN_B gw $IP_LORA_B



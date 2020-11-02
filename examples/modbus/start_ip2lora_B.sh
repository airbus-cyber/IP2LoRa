#!/bin/sh

IP_LORA_A=172.16.10.1
IP_LAN_A=192.168.1.2
NET_LAN_A=192.168.1.0
MASK_LAN_A=24

IP_LORA_B=172.16.10.2
IP_LAN_B=192.168.2.2
NET_LAN_B=192.168.2.0
MASK_LAN_B=24


# ensure no previous running instance
./stop_ip2lora.sh 2>/dev/null && sleep 5

# flush iptables rules
iptables -F
iptables -t nat -F


# start IP2Lora
echo "Starting IP2Lora..."
./ip2lora.py -d config_st_B.py > /tmp/ip2lora.log 2>&1 &
#./ip2lora.py -d config_rak811_B.py > /tmp/ip2lora.log 2>&1 &
#./ip2lora.py -d config_lostick_B.py > /tmp/ip2lora.log 2>&1 &
echo $! > /var/run/ip2lora.pid

sleep 10

# activate forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# Add route to site A network
route add -net $NET_LAN_A/$MASK_LAN_A gw $IP_LORA_A

# activate NAT (PLC may already have another default gateway)
iptables -t nat -A POSTROUTING -d 192.168.2.1 -j SNAT --to-source $IP_LAN_B


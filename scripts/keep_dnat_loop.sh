#!/system/bin/sh
while true; do
  iptables -t nat -C OUTPUT -p tcp -d 47.98.142.149 --dport 443 -j DNAT --to-destination 127.0.0.1:8080 2>/dev/null || iptables -t nat -A OUTPUT -p tcp -d 47.98.142.149 --dport 443 -j DNAT --to-destination 127.0.0.1:8080
  iptables -t nat -C OUTPUT -p tcp -d 183.247.246.67 --dport 443 -j DNAT --to-destination 127.0.0.1:8080 2>/dev/null || iptables -t nat -A OUTPUT -p tcp -d 183.247.246.67 --dport 443 -j DNAT --to-destination 127.0.0.1:8080
  iptables -t nat -C OUTPUT -p tcp -d 111.32.210.108 --dport 443 -j DNAT --to-destination 127.0.0.1:8080 2>/dev/null || iptables -t nat -A OUTPUT -p tcp -d 111.32.210.108 --dport 443 -j DNAT --to-destination 127.0.0.1:8080
  iptables -t nat -C OUTPUT -p tcp -d 183.247.246.229 --dport 443 -j DNAT --to-destination 127.0.0.1:8081 2>/dev/null || iptables -t nat -A OUTPUT -p tcp -d 183.247.246.229 --dport 443 -j DNAT --to-destination 127.0.0.1:8081
  sleep 2
done

#!/bin/bash
# UFW rules for virtual-tunnel-vnic
# Run these to restore firewall rules from scratch

sudo ufw allow OpenSSH
sudo ufw allow http
sudo ufw allow https
echo y | sudo ufw enable

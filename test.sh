#!/bin/bash

# Test script for Pi - checks network settings, app functionality, and service status

# Check network configuration persistence
if [ -f /etc/network/interfaces ]; then
  echo "Network config file exists"
  grep "auto eth0" /etc/network/interfaces || echo "Missing auto eth0 line"
fi

# Test connectivity
ping -c 4 8.8.8.8

# Check if app service is running
systemctl is-active app-service || echo "App service not active"

# Check logs for errors
journalctl -u app-service --since "1 hour ago" | grep -i error || echo "No errors found in logs"

# Simulate reboot and check network settings again
sudo systemctl restart networking
sleep 10

# Re-check network config after reboot simulation
if [ -f /etc/network/interfaces ]; then
grep "auto eth0" /etc/network/interfaces || echo "Network config changed after reboot simulation"
fi
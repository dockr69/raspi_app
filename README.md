## Simulated Testing
To test in a simulated environment:
1. Build the Docker image: `docker build -t pi-test .`
2. Run the container: `docker run -it pi-test`
3. Execute the test script inside the container: `chmod +x test.sh && ./test.sh`
4. Verify network configuration persistence after simulated reboot
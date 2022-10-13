[![CodeQL](https://github.com/toreamun/hanetprobe/actions/workflows/codeql.yml/badge.svg?style=for-the-badge)](https://github.com/toreamun/hanetprobe/actions/workflows/codeql.yml)
[![License](https://img.shields.io/github/license/toreamun/hanetprobe?style=for-the-badge)](LICENSE)
![Project Maintenance](https://img.shields.io/badge/maintainer-Tore%20Amundsen%20%40toreamun-blue.svg?style=for-the-badge)
[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-orange.svg?style=for-the-badge)](https://www.buymeacoffee.com/toreamun)

# Home Assistant net probe
Network uptime monitor publishing to Home Assistant MQTT discovery.

Supports ICMP ping and DNS lookup. Sensors publishes round-trip-time, jitter and loss.

You can use this application to create multiple probes that reports to [Home Assistant](https://www.home-assistant.io) using [MQTT](https://mqtt.org/). 
Home Assistant [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) must be configured with discovery enabled (default).

A configuration file has to be created. See detals [bellow](#configuration)
Example of minimal configuration file (default config filename is probe.yaml):


```yaml
mqtt:
   host: 192.168.1.10

probes:
  dns:
    - name: google
      target-adr: 8.8.8.8
```

## Running
### Using docker
You can run the application using docker. 
```console
docker run --volume=$(pwd)/probe.yaml:/app/config/probe.yaml ghcr.io/toreamun/hanetprobe:master
```

docker-compose.yaml example:
```yaml
version: "3"
services:
  probe:
    container_name: ha-net-probe
    image: ghcr.io/toreamun/hanetprobe:master
    restart: unless-stopped
    volumes:
      - ./probe.yaml:/app/config/probe.yaml
```

Create a docker-compose.yaml file and a probe config file named probe.yaml file in the same folder. You can run `docker-compose up --detach` to start the container, and `docker-compose down` to stop it. Output from container can be viewed with `docker-compose logs -f`. You can update docker image with `docker-compose pull`.

### Python
```console
python3 probe_app.py
```

## Probes
### DNS probe
DNS probes uses UDP DNS queries to monitor round-trip-time and packet loss. The probe keeps a limited history and calculates average round-trip-time, jitter and percent packet loss.

### ICMP ping probe
ICMP ping probes uses ICMP ping packets to monitor round-trip-time and packet loss. The probe keeps a limited history and calculates average round-trip-time, jitter and percent packet loss.


## Configuration
The configuration can contain multiple probes.

Example of two probes:
```yaml
service:
  id: router-probe
  name: my-net-probe
  log-level: INFO

mqtt:
  host: 192.168.1.10

probes:
  dns:
    - name: google
      target-adr: 8.8.8.8
    - name: cloudflare
      target-adr: 1.1.1.1
      interval: 10
      timeout: 0.5
      query-names: google.com microsoft.com
      history-len: 50
  ping:
    - name: google
      target-adr: 8.8.8.8
    - name: cloudflare
      target-adr: 1.1.1.1
      interval: 10
      timeout: 0.5
      history-len: 50
      
```

### service
- id: used to generate unique device id. Defaults host name.
- name: used for Home Assistant device name.
- log-level: Can be CRITICAL, ERROR, WARNING, INFO or DEBUG. Default is INFO.

### mqtt
- host: MQTT server host address. Required.
- port: Optional. Defaults to 1883.
- transport: tcp or websockets. Defaults to tcp.
- username: optional.
- password: optional.

### probes
#### dns
- name: probe name. Used as base for home assistant entity names.
- target-adr: IP address of dns server to monitor.
- interval: time between each DNS query. Defaults to 1.0 (1 second).
- timeout: time to wait for reply. Defaults to 1.0 (1 second).
- history-len: length of history (used to calculate jitter and averate rtt and loss). Defaults to  100.
- publish-precision: decimals in published values. Defaults to 1.
- query-names: Optional. Names (seperated by space) to use in DNS lookup. A random name is selected from the list.

#### ping
- name: probe name. Used as base for home assistant entity names.
- target-adr: IP address of server to monitor.
- interval: time between each DNS query. Defaults to 1.0 (1 second).
- timeout: time to wait for reply. Defaults to 1.0 (1 second).
- history-len: length of history (used to calculate jitter and averate rtt and loss). Defaults to  100.
- publish-precision: decimals in published values. Defaults to 1.
- payload-size: ping packet size. Defaults to 56.

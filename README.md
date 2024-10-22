[![CodeQL](https://github.com/toreamun/hanetprobe/actions/workflows/codeql.yml/badge.svg)](https://github.com/toreamun/hanetprobe/actions/workflows/codeql.yml)
[![License](https://img.shields.io/github/license/toreamun/hanetprobe)](LICENSE)
![Project Maintenance](https://img.shields.io/badge/maintainer-Tore%20Amundsen%20%40toreamun-blue.svg)
[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-orange.svg)](https://www.buymeacoffee.com/toreamun)

# Home Assistant net probe
Network uptime monitor publishing to Home Assistant MQTT discovery.

Supports ICMP ping and DNS lookup. Sensors publishes round-trip-time, jitter and loss.

You can use this application to create multiple probes that reports to [Home Assistant](https://www.home-assistant.io) using [MQTT](https://mqtt.org/).
Home Assistant [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) must be configured with discovery enabled (default).

A configuration file has to be created. See details [below](#configuration)
Example of minimal configuration file (default config filename is probe.yaml):


```yaml
mqtt:
   host: 192.168.1.10

probes:
  dns:
    - name: google
      target-adr: 8.8.8.8
```

You will find the the probe as a device in MQTT integration:
![image](https://user-images.githubusercontent.com/12134766/195714262-ff6e3153-144e-4a99-815c-bcb5ac2cf61e.png)


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
The configuration can contain multiple probes and [Python logging schema](https://docs.python.org/3/library/logging.config.html#configuration-dictionary-schema) can be used in configuration:

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

Example using [Python logging config schema](https://docs.python.org/3/library/logging.config.html#configuration-dictionary-schema):
```yaml
service:
  id: router-probe
  name: my-net-probe
mqtt:
  host: 192.168.1.10
probes:
  ping:
    - name: google
      target-adr: 8.8.8.8
logging:
  version: 1
  formatters:
    simple:
      format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  handlers:
    console:
        class: logging.StreamHandler
        level: DEBUG
        formatter: simple
        stream: ext://sys.stdout
    file:
        class : logging.handlers.RotatingFileHandler
        formatter: simple
        filename: hanetprobe.log
        maxBytes: 2621440
        backupCount: 3
  root:
    level: INFO
    handlers: [console,file]
    propagate: no
  loggers:
    ping_probe:
      level: WARNING
      propagate: yes
    dns_probe:
      level: WARNING
      propagate: yes
    publish:
      level: INFO
      propagate: yes

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

### compound:
Uses multiple probes to change status when all are up or down.

```yaml
compound:
  all-down:
    - name: "multiple"
      probes:
      - type: dns
        name: cloudflare
      - type: dns
        name: google
```


### logging:
See [Python logging config schema](https://docs.python.org/3/library/logging.config.html#configuration-dictionary-schema).

## Grafana
[Grafana](https://github.com/hassio-addons/addon-grafana) with [InfluxDB](https://github.com/hassio-addons/addon-influxdb) is a great way of visualizing data from the probe. Here are some examples of comparing [Telia Trådløst bredbånd](https://www.telia.no/internett/tradlost-bredband/) and [Telenor Trådløst bredbånd](https://www.telenor.no/privat/internett/tradlost-bredband/) Fixed Wireless Access 4G connectivity to Cloudflare DNS. Boths modem/antennas was located at the same place pointing at the same shared tower.

![image](https://user-images.githubusercontent.com/12134766/195715672-785f2f62-9d8a-44b5-ad41-52aa145b1b01.png)

![image](https://user-images.githubusercontent.com/12134766/195716675-fc58d478-dfe3-4605-b547-4e892c1d0c05.png)

![image](https://user-images.githubusercontent.com/12134766/195716790-eb0d0fb9-3c43-439c-99f5-8c75ad205937.png)





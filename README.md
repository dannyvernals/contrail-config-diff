# contrail-config-diff
Get Contrail / OpenStack configuration files and compare them against previous versions

## Introduction
Contrail is typically deployed via automated tools such as: juju, RHOSP, helm, ansible etc.  
Sometimes issues can happen on these platforms and bad config can be pushed out to the platform.  
Also planned work can happen that can break Contrail components.

Configuration is deployed in many different locations (hosts and files) so it can take time to find the issues.  
This script aims to solve some of those problems.  
It grabs configuration files from remote hosts and then diffs the files against previous versions.  
The script can be run before and after maintainance or regularly against a known good template to highlight problems.
The config can then be quickly corrected.

## Configuration
The script takes input from 2 yaml files, one documents the remote component IPs (controller, analytics, heat etc).  
The other documents the config files you are interested in.
The files are completely configurable but examples have been included in the repo.
As Contrail / Openstack configs are typically only root readable, the script obtains them via a 'sudo cat' over an ssh session.  
Currently the script only works if the user used with SSH can passwordless sudo on the remote component servers.

If you want to generate the IPs yaml file from a 'juju status' you can do this automatically with the script.
Currently other deployment methods require the file to be generated manually.

** WARNING **   
Lots of the files that are obtained contain passwords (why they are only root readable on the remote systems).
The script chmods all files it creates to 600 and by default attempts obsfucate passwords but it has not been comprehensively audited.
That said it will only work from a system / user that has root access (via sudo) on the remote servers so a good security posture is already assumed for the system.

##  Example IPs file
Specify the IPs of the components you want to query.  

```yaml
contrail-agent:
- 172.16.0.134
contrail-analytics:
- 172.16.0.104
contrail-analyticsdb:
- 172.16.0.144
contrail-controller:
- 172.16.0.102
contrail-haproxy:
- 172.16.0.142
heat:
- 172.16.0.143
neutron:
- 172.16.0.103
```

## Example Config file
Specify the files you want to grab and diff
```yaml
heat:
  - /etc/heat/heat.conf

contrail-haproxy:
  - /etc/haproxy/haproxy.cfg

neutron:
  - /etc/neutron/neutron.conf
  - /etc/neutron/plugins/opencontrail/ContrailPlugin.ini

contrail-agent:
  - /etc/contrail/common_vrouter.env
  - /etc/contrail/vrouter/docker-compose.yaml
  - /etc/contrail/contrail-vrouter-agent.conf
  - /etc/nova/nova.conf

contrail-controller:
  - /etc/contrail/common_web.env
  - /etc/contrail/webui/docker-compose.yaml
  - /etc/contrail/redis/docker-compose.yaml
  - /etc/contrail/config_database/docker-compose.yaml
  - /etc/contrail/config_api/docker-compose.yaml
  - /etc/contrail/control/docker-compose.yaml
  - /etc/contrail/common_config.env
  - /etc/contrail/redis.env

contrail-analyticsdb:
  - /etc/contrail/common_analyticsdb.env
  - /etc/contrail/analytics_database/docker-compose.yaml

contrail-analytics:
  - /etc/contrail/analytics_snmp/docker-compose.yaml
  - /etc/contrail/redis/docker-compose.yaml
  - /etc/contrail/analytics/docker-compose.yaml
  - /etc/contrail/analytics_alarm/docker-compose.yaml
  - /etc/contrail/redis.env
  - /etc/contrail/common_analytics.env
```

## Examples
Below contains some examples for how to run the script.  
For all options please see ```python3 contrail-config-diff.py -h```

### 1) Basic Operation
The script will by default use the sepecified yaml files to obtain config files and compare them against a previous run.
If you are running the script for the first time, just mkdir the directory to compare against.
```shell
danny@newtop:~/contrail-config-diff$ mkdir dummy_dir
danny@newtop:~/contrail-config-diff$ python3 contrail-config-diff.py unit_ips.yaml files_no_ssl.yaml 17-07-20 dummy_dir
getting 'contrail-agent' data
from '172.16.0.134'
getting 'contrail-analytics' data
from '172.16.0.104'
getting 'contrail-analyticsdb' data
from '172.16.0.144'
getting 'contrail-controller' data
from '172.16.0.102'
getting 'contrail-haproxy' data
from '172.16.0.142'
getting 'heat' data
from '172.16.0.143'
getting 'neutron' data
from '172.16.0.103'
====================================================================================================
Files missing in the 'dummy_dir' directory: 
contrail-agent
contrail-analytics
contrail-analyticsdb
contrail-controller
contrail-haproxy
heat
neutron
```
Obviously there are no files to compare against if this is the first time you've run the script.

### 2) Only Diff
If you have previously gathered output you can skip the gathering step and only execute a diff on the files

```shell
danny@newtop:~/contrail-config-diff$ python3 contrail-config-diff.py -d unit_ips.yaml files_no_ssl.yaml 16-07-20 17-07-20
====================================================================================================
16-07-20/contrail-haproxy/172.16.0.142/_etc_haproxy_haproxy.cfg
17-07-20/contrail-haproxy/172.16.0.142/_etc_haproxy_haproxy.cfg

21c21
< CONTROL_NODES=172.16.0.102
---
> CONTROL_NODES=172.16.0.103

====================================================================================================
16-07-20/heat/172.16.0.143/_etc_heat_heat.conf
17-07-20/heat/172.16.0.143/_etc_heat_heat.conf

86c86
< api_server = 172.16.0.102
---
> api_server =  
```

Note that standard diff styles of 'normal', 'context' and 'unified' are available if you want to use the diff output to 'patch' the modified files back to working config.

### 3) Use juju to generate the IPs file
If you are using juju to deploy Contrail, you can use the output of 'juju status' to generate the IPs file automatically.
Below shows using a juju status via a subprocess within the script but you can also read from a file with the '-f' option.

The output will be saved to the IPs file specified on the command line for future use
```
danny@newtop:~/contrail-config-diff$ python3 contrail-config-diff.py -g unit_ips.yaml files_no_ssl.yaml 16-07-20 17-07-20
getting juju status
generating and writing component IPs file from 'juju status' output
output directory already exists, old files will be deleted, proceed?, y/n:y
getting 'contrail-agent' data
from '172.16.0.134'
getting 'contrail-analytics' data
from '172.16.0.104'
getting 'contrail-analyticsdb' data
from '172.16.0.144'
getting 'contrail-controller' data
from '172.16.0.102'
getting 'contrail-haproxy' data
from '172.16.0.142'
getting 'heat' data
from '172.16.0.143'
getting 'neutron' data
from '172.16.0.103'
====================================================================================================
54d53
<     server contrail-controller-1 172.16.0.152:8143 cookie 172.16.0.152 weight 1 maxconn 1024 check port 8143
77d75
<     server contrail-controller-1 172.16.0.152:8082 check inter 2000 rise 2 fall 3
```

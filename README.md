# contrail-config-diff
Get Contrail / OpenStack configuration files and compare them against previous versions

## Introduction
Contrail is typically deployed via automated tools such as: juju, RHOSP, helm, ansible etc.  
Sometimes issues can happen on these platforms and bad config can be pushed out to the platform.  
Also planned work can happen that can break Contrail components.  

This script focuses on juju deployments,although most of the code should be reusable (with a little tweaking) for other methods. 

Configuration is deployed in many different locations (hosts and files) so it can take time to find the issues.  
This script aims to solve some of those problems.  
It grabs configuration files from remote hosts and then diffs the files against previous versions.  
The script can be run before and after maintainance or regularly against a known good template to highlight problems.
The config can then be quickly corrected.

The script has 2 modes:
### 1) push config into a git repo.  
This can be used to track the changes to configuration state over time and be a store for a 'known good' 
working cofiguration.  It can also help pinpoint when changes occured and correlate them to changes in DC behaviour.
Typically the script would be executed in this mode via cron.
### 2) Execute before and after a planned work event.
Here configs are stored in plain text and a diff produced when the 'after' snapshot is captured.
It allows an operator to quickly assess if their change was successful or if anything unexpected has changed.

## Configuration
The script takes input from 3 yaml files: 
* one documents the remote component IPs (controller, analytics, heat etc).  
* one documents the config files you are interested in, on the remote components
* one contains a snapshot of 'juju show-controller' (needed to lookup the juju controller: IP, CA cert, port, model name etc etc)

The files are configurable, examples have been included in the repo.

As Contrail / Openstack configs are typically only root readable, the script obtains them via a 'sudo cat' over an ssh session.  
Currently the script only works if the uid used with SSH can passwordless sudo on the remote component servers.

If you want to generate the IPs yaml file from a 'juju status' you can do this automatically with the script using '-g'.

** WARNING **   
Lots of the files that are obtained contain passwords (why they are only root readable on the remote systems).
The script chmods all files it creates to 600 and by default attempts obsfucate passwords but it has not been comprehensively audited.
That said it will only work from a system / user that has root access (via sudo) on the remote servers so a good security posture is already assumed for the system.


## Examples
Below contains some examples for how to run the script.  
For all options please see ```python3 contrail_config_diff.py -h```

### 1) Push Configs into a git repo
```
python ./contrail_config_diff.py unit_ips.yaml files_no_ssl.yaml juju_file.yaml admin -r test-repo
```
Above line will produce no output, std_err & std_out are redirected to ./logs
Typically you'd instantiate that in cron or via another automated execution mechanism

Configs will be outputted to ./repos/${repo_name}
Standard git CLI can then be used to track config state e.g.
```
contrail-config-diff/repos/test-repo$ git log
commit 439ebdb21d8b6328f1a4aaf581604d47de7b12fa (HEAD -> master)
Author: Danny Vernals 
Date:   Thu Nov 5 13:40:26 2020 +0000

    automated commit

commit de29bee12b4e0b8ad0863c85a0a7bd9b64d1dec7
Author: Danny Vernals 
Date:   Thu Nov 5 13:39:48 2020 +0000

    test

commit aec4565e67fd16c63504fefb7a2978798c8b1100
Author: Danny Vernals 
Date:   Thu Nov 5 12:59:56 2020 +0000

    automated commit

commit 33034fff0c78d9608cb8fc1fccd7897c81e4b99d
Author: Danny Vernals 
Date:   Thu Nov 5 12:59:14 2020 +0000

    test commit

```

```diff
sdn/contrail-config-diff/repos/test-repo$ git show master
commit 439ebdb21d8b6328f1a4aaf581604d47de7b12fa (HEAD -> master)
Author: Danny Vernals 
Date:   Thu Nov 5 13:40:26 2020 +0000

    automated commit

diff --git a/juju_apps.txt b/juju_apps.txt
index 453da11..8d467c9 100644
--- a/juju_apps.txt
+++ b/juju_apps.txt
@@ -3,7 +3,7 @@ contrail-analytics        cs:~juniper-os-software/contrail-analytics-21      con
 contrail-analyticsdb      cs:~juniper-os-software/contrail-analyticsdb-21    contrail-analyticsdb/0         2011-46   
 contrail-command          cs:~juniper-os-software/contrail-command-3         contrail-command/0             2011-46   
 contrail-controller       cs:~juniper-os-software/contrail-controller-23     contrail-controller/0          2011-46   
-contrail-haproxy          cs:haproxy-55                                      contrail-haproxy/0             TEST          
+contrail-haproxy          cs:haproxy-55                                      contrail-haproxy/0                       
 contrail-keystone-auth    cs:~juniper-os-software/contrail-keystone-auth-21  contrail-keystone-auth/0                 
 easyrsa                   cs:~containers/easyrsa-333                         easyrsa/0                      3.0.1     
 glance                    cs:glance-301                                      glance/0                       16.0.1 
```

### 2) Execute before and after a planned work event
Note '-g' can be used with both modes, it means the 'ips_file.yaml' will be auto generated from juju 

```
sdn/contrail-config-diff$ python ./contrail_config_diff.py unit_ips.yaml files_no_ssl.yaml juju_file.yaml admin -g -m test-upgrade -w before
getting juju status
generating and writing component IPs file from 'juju status' output
getting 'contrail-analytics' data
from '172.16.0.111'
getting 'contrail-analyticsdb' data
from '172.16.0.142'
getting 'contrail-command' data
from '172.16.0.136'
getting 'contrail-controller' data
from '172.16.0.110'
getting 'contrail-keystone-auth' data
from '172.16.0.105'
getting 'haproxy' data
from '172.16.0.108'
getting 'heat' data
from '172.16.0.133'
getting 'neutron-api' data
from '172.16.0.140'
getting 'nova-compute' data
from '172.16.0.125'
```

```
sdn/contrail-config-diff$ python ./contrail_config_diff.py unit_ips.yaml files_no_ssl.yaml juju_file.yaml admin -g -m test-upgrade -w after
getting juju status
generating and writing component IPs file from 'juju status' output
output directory already exists, old files will be deleted, proceed?, y/n:y
getting 'contrail-analytics' data
from '172.16.0.111'
getting 'contrail-analyticsdb' data
from '172.16.0.142'
getting 'contrail-command' data
from '172.16.0.136'
getting 'contrail-controller' data
from '172.16.0.110'
getting 'contrail-keystone-auth' data
from '172.16.0.105'
getting 'haproxy' data
from '172.16.0.108'
getting 'heat' data
from '172.16.0.133'
getting 'neutron-api' data
from '172.16.0.140'
getting 'nova-compute' data
from '172.16.0.125'
====================================================================================================
./maintenances/test-upgrade/before/juju_apps.txt
./maintenances/test-upgrade/after/juju_apps.txt
4c4
< contrail-command          cs:~juniper-os-software/contrail-command-3         contrail-command/0             1912.32   
---
> contrail-command          cs:~juniper-os-software/contrail-command-3         contrail-command/0             2011-46   

====================================================================================================
./maintenances/test-upgrade/before/haproxy/172.16.0.108/_etc_haproxy_haproxy.cfg
./maintenances/test-upgrade/after/haproxy/172.16.0.108/_etc_haproxy_haproxy.cfg
50c50
<     server contrail-controller-0 172.16.0.199:8143 cookie 172.16.0.199 weight 1 maxconn 1024 check port 8143
---
>     server contrail-controller-0 172.16.0.110:8143 cookie 172.16.0.110 weight 1 maxconn 1024 check port 8143
```

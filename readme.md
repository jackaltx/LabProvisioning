# Overview

This is for local Debian 12 linux machine provisioning. I prefer Centos, but it is no longer.  Rocky has been a rocky ride.
So for now I am limiteing my work to Debian.

# Usage

I am provisioning VM and metal Debian 12 machines for my lab.  I need to spin up a new system to test an idea. 
Experiment on an existing system can end up with either instability or loss of what was done.  Setting up a baseline with
a clean system is time consuming.  To get around those issues I use a provisioning tool to set an environment. 

In the past I used to use puppet for this task. However the overhead of installing ruby as well as the other required packages was too heavy.  Ansible came along and it works. I don't think it works as well as puppet, but it is fairly light weight and most time python is more accepted. 

This repository is a small collection of ansible scripts designed to bring up a usable platorm.  First I install ansible using a package
manager. Then to do make this work I either install enough to check out this repo from github or mount the code from a nfs directory, or use a flash drive.

Tnen I use the first playbook to bring the platform into the fold.  From the base of the directory.

``` 
sudo ansible-playbook first.yml
```
or

```
ansible-playbook -K first .yml
```

From there I add what I need.  In the end, I remove the directory.   It's not elegant like using a provisioning service, but it fits my ever changing needs.

I did not do a good job of setting the "become" flag.  I am going back to work the code. 

# Concept notes

##  Ansible inventory

I have chosen a yml structure so I effectively use variables for specific configurations.  For example,  first I need to create an influxd server to generate the access tokens for the telegraf clients.  A handy command to know is:

```
ansible-inventory -i inventory --list
{
    "_meta": {
        "hostvars": {
            "localhost": {
                "influx_level": "error",
                "telegraf_influx_token": "br549==",
                "telegraf_influx_url": "monitor.mydomain.com"
            }
        }
    },
    "all": {
        "children": [
            "ungrouped",
            "mylab"
        ]
    },
    "mylab": {
        "hosts": [
            "localhost"
        ]
    }
}
```

The only host being worked on is localhost, which is a assigned to a "mylab" group.  Ansible [variable precidence](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable) is a bit complicated and confounds me.  


##  Ansible secrets

I need to distribute sensitive settings in a "free" way, as we all know:  *it costs to keep secrets secret*.
In that endeavor I am using a couple of tricks to keep unencrypted secrets out of this repository.

First trick:   ansible will take an executable file for the password.  So I created  a program in the file .vault-pass

```
#!/usr/bin/env python3
import os
print(os.environ['PROVISION_VAULT_PASSWORD'])
```

This returns environment variable *PROVISION_VAULT_PASSWORD*. for now I am setting it in my.bashrc file.
Which is ok for now. 

The second trick is to use the ansible.cfg file to set the default password file. Like so:

```
# If set, configures the path to the Vault password file as an alternative to
# specifying --vault-password-file on the command line.
#vault_password_file = /path/to/vault_password_file
vault_password_file = ./.vault-pass
```

So only the following line needs to be in my .bashrc file"

> export PROVISION_VAULT_PASSWORD= yourProjectassword

I use the inventory file to set the variables I need

```
    promtail_loki_url: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          66323533376364663634653733316364326137616130663039616330343830393836626466333930
          3134336564316639623363313735633930356537356331360a313138623665353266646266363564
          35663965323433636263343031373934376235613161333661656637316438653034653861383864
          3531306331616264310a396566613761326165633763653934363434633163303863316135303839
          39383132373865396266343766336439616539623532373363346535393661636638
```

To make that string

```
$ ansible-vault encrypt_string "http://xxx.yyy.zzz:3100" --name 'promtail_loki_url'

Encryption successful
promtail_loki_url: !vault |
          $ANSIBLE_VAULT;1.1;AES256      
          66323533376364663634653733316364326137616130663039616330343830393836626466333930
          3134336564316639623363313735633930356537356331360a313138623665353266646266363564
          35663965323433636263343031373934376235613161333661656637316438653034653861383864
          3531306331616264310a396566613761326165633763653934363434633163303863316135303839
          39383132373865396266343766336439616539623532373363346535393661636638
```
##  Podman

I am starting to test containers.  Podman as a rootless-systemd process is intriquing. So far my attempts
have not been successful.  Rooted works as advertised. I will document more in the wiki.  

The podman role will manage install and uninstall.

## LXC

Yet another cool container.  So far I am not having any luck.  I will likely use a [backport](https://en.wikipedia.org/wiki/Backporting)
to install a newer version. Debian's release cycle can be slow on package integration.  Which is both a good and bad thing.

Odds are I will be moving to [incus](https://linuxcontainers.org/incus/introduction/)

## Minikube

my goal is a pure podman install. the 'start-minikube' support script makes that happen.

#  Future

The roles in "Provision Collection" will be reusable in later projects. 

## In work list

Environment installations:

- Grafana
- Openstack or Ghost or Bookstack (
- [fail2ban](https://github.com/fail2ban/fail2ban)
- [ossec](https://www.ossec.net/)
- [grassmarlin](https://linuxcontainers.org/incus/introduction/)
- ...

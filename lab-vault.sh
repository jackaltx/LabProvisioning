#!/bin/sh

ansible-vault $1 ./ProvisionCollection/telegraf/files/etc-default-telegraf-cloud
ansible-vault $1 ./ProvisionCollection/telegraf/files/etc-default-telegraf-local
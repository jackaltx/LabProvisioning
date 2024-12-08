#!/bin/bash

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

pip install --upgrade pip

# Core packages
pip install molecule
pip install ansible-core==2.16.12
pip install ansible-lint
pip install requests
pip install proxmoxer
pip install dnspython  # For DNS lookups
pip install jmespath

# Ansible collections
ansible-galaxy collection install community.general:10.0.1

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
from ansible.plugins.vars import BaseVarsPlugin
from ansible.utils.display import Display

display = Display()

DOCUMENTATION = '''
    vars: project_vars
    short_description: Set project root variable
    description: Determines project root based on ansible.cfg location
    options: {}
    author: YourName
    version_added: "1.0"
'''

class VarsModule(BaseVarsPlugin):
    def get_vars(self, loader, path, entities, cache=True):
        super(VarsModule, self).get_vars(loader, path, entities)
        
        # Use ansible_config_file from entities if available
        for entity in entities:
            if hasattr(entity, 'vars') and 'ansible_config_file' in entity.vars:
                config_path = os.path.realpath(entity.vars['ansible_config_file'])
                project_root = os.path.dirname(config_path)
                display.v(f'Found real project root from config: {project_root}')
                return {'project_root': project_root}
        
        # Fallback to searching from current directory
        current_dir = os.path.realpath(os.getcwd())
        while current_dir != '/':
            cfg_path = os.path.join(current_dir, 'ansible.cfg')
            if os.path.exists(cfg_path):
                display.v(f'Found real project root from search: {current_dir}')
                return {'project_root': current_dir}
            current_dir = os.path.dirname(current_dir)
        
        # Ultimate fallback
        cwd = os.path.realpath(os.getcwd())
        display.v(f'Falling back to real current directory: {cwd}')
        return {'project_root': cwd}
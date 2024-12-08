No, you should not use the system Python for development and testing work like this. It's better practice to use a Python virtual environment for several reasons:

1. Safety: System Python is used by your OS and other system tools. Modifying its packages could break system functionality.
2. Isolation: Virtual environments keep project dependencies separate from each other and the system.
3. Reproducibility: Makes it easier to track and share exact dependency versions.
4. No sudo required: You don't need elevated privileges to install packages.

Here's what I recommend instead:

```bash
# Install python3-venv if you don't have it
sudo apt install python3-venv

# Create a virtual environment in your project directory
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Now install the required packages (no sudo needed)
pip install molecule molecule-plugins[proxmox] ansible-core
```

When you're done working:
```bash
deactivate  # Exits the virtual environment
```

You can add to your .gitignore:
```
venv/
```

To make it easier to use, you could create a script called `setup-dev.sh`:
```bash
#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install molecule molecule-plugins[proxmox] ansible-core
```

Then whenever you need to work on the project:
```bash
source venv/bin/activate
```
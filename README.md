Python for acquiring data to make heatmaps and actually making them.

## Setup steps

1. install distro python
2. install virtualenv
3. install the exact version of the interpreter you need
4. ```cd project_folder```
5. ```pyvenv venv```  NOTE: if the default python install is <3.3 you will need
to use the exact interpreter version located at bin/pyenv
6. ```pyvenv -p path_to_exact_interpreter venv```  NOTE: not needed if you use
pyvenv from the desired interp
7. ```git clone https://github.com/tgbugs/heatmaps.git```
8. ```source venv/bin/activate```
8. ```python ```  NOTE: this will change if this is released as a package for pip

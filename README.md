Python for acquiring data to make heatmaps and actually making them.

## Setup steps

0. install postgres devlibs (postgresql-devel)
0. install libxml2 devlibs (libxml2-devel, libxslt-devel)
1. install distro python
2. install virtualenv  #only if below 3.4 or 3.3
3. install the exact version of the interpreter you need
4. ```cd project_folder```
5. ```pyvenv venv```  NOTE: if the default python install is <3.3 you will need
to use the exact interpreter version located at bin/pyenv
6. ```pyvenv -p path_to_exact_interpreter venv```  NOTE: not needed if you use
pyvenv from the desired interp
7. ```git clone https://github.com/tgbugs/heatmaps.git```
8. ```source venv/bin/activate```
9. ```cd heatmaps; python setup.py install```  NOTE: needs work
0. ```python dbsetup.py```
0. On centos you will need to make sure httpd-devel is installed
0. in the venv run ```pip install mod_wsgi```
0. sudo heatmaps/venv/bin/mod_wsgi-express install-module
0. probably going to have to monkey around with stuff to get the venv to actually work
1. set PYTHONPATH=path to include the parent direclty you cloned the repository to 
2. install heatmaps.wsgi to wherever you keep wsgi files
3. install heatmaps.conf to wherever you keep apache config files


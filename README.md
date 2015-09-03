Python for acquiring data to make heatmaps and actually making them.

## matplotlibrc
You must set
backend : Agg
in ~/.config/matplotlib/matplotlibrc

## Setup steps

0. install all the following libs (centos version): ```yum install postgresql-libs postgresql-devel libxml2 libxml libxslt libxml-dev libxml2-dev libxml2-devel libxslt-dev libxslt-devel httpd-devel```
1. install distro python3
4. as root you need to run once
```echo PYTHONPATH=path_to_distro_python3 >> /etc/sysconfig/httpd```
so that mod_wsgi can run on the correct interpreter
3. install the exact version of the interpreter you need
to use the exact interpreter version located at bin/pyenv

For database setup (does not have to be run on production server)
7. ```git clone https://github.com/tgbugs/heatmaps.git```
8. ```cd heatmaps```
0. ```python3 dbsetup.py```

Production env setup
0. venv_setup.sh needs to be run on the production server

Build the zip for production? Seems silly? Who knows.
4. run the setup .sh scripts and then run the deploy

Things than need to happen post deploy on the production server
3. install heatmaps.conf to wherever you keep apache mod config files


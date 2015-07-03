# create our venv for deploy, run as root
PYVENV="/usr/local/anaconda3/bin/pyvenv"
INSTALL_DIR="/var/virtualenvs/"
VENV=heatmap_venv

mkdir -p $INSTALL_DIR
rm -rf $INSTALL_DIR$VENV &&
cd $INSTALL_DIR &&
$PYVENV $VENV &&
source heatmap_venv/bin/activate &&
pip install setuptools psycopg2 requests lxml numpy flask ipython mod_wsgi &&
pip freeze > heatmap_venv/requirements.txt &&
mod_wsgi-express install-module &&
deactivate


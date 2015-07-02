# create our venv for deploy
PYVENV="/usr/local/anaconda3/bin/pyvenv"
BUILD_DIR="/tmp/venv_build"
INSTALL_DIR="/var/virtualenvs/"

rm -rf $BUILD_DIR
mkdir $BUILD_DIR
cd $BUILD_DIR
$PYVENV heatmap_venv
source heatmap_venv/bin/activate
pip install setuptools psycopg2 requests lxml numpy flask ipython mod_wsgi
pip freeze > heatmap_venv/requirements.txt
mod_wsgi-express install-module
deactivate
mv headmap_venv $INSTALL_DIR
cd ..
rmdir $BUILD_DIR


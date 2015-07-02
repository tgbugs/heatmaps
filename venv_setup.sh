# create our venv for deploy
PYVENV="/usr/local/anaconda3/bin/pyvenv"
BUILD_DIR="/tmp/venv_build"

cd $BUILD_DIR
$PYVENV venv
source venv/bin/activate
pip install setuptools psycopg2 requests lxml numpy flask ipython
deactivate
zip -r venv_deploy.zip venv


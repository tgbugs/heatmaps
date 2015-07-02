# build script can be run as any user
BUILD_DIR="/tmp/heatmap_build"

rm -rf $BUILD_DIR
mkdir $BUILD_DIR
cd $BUILD_DIR
git clone https://github.com/tgbugs/heatmaps.git
ln -s heatmaps/heatmaps.wsgi
zip -ry heatmap_deploy.zip .


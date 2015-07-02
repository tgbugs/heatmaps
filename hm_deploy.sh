INSTALL_DIR="/var/www/heatmaps"
HMZIP_SOURCE="/tmp/heatmap_build/heatmap_deploy.zip"
HMZIP_TARGET="/tmp/heatmap_deploy.zip"
SERVER="kaa"
USER="user"

# mv the current to the old, keeping one backup
ssh $USER@$SERVER "mv ${HMZIP_TARGET} _old_${HMZIP_TARGET}"
# scp files over
scp $HMZIP_SOURCE $USER@$SERVER:$HMZIP_TARGET
# this should be run remotely
ssh $USER@$SERVER "sudo rm -rf ${INSTALL_DIR}"
ssh $USER@$SERVER "unzip -o ${HMZIP_TARGET} -d /tmp/heatmaps"
ssh $USER@$SERVER "sudo mv /tmp/heatmaps ${INSTALL_DIR}"


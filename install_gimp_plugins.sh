#!/bin/bash

GIMP_PLUGINS_DIR=~/.gimp-2.8/plug-ins
MY_PLUGINS_DIR=$PWD/gimp-plugins

PLUGIN_EXPORT_JSON=gimp_export_json.py
PLUGIN_EXPORT_SKIN=gimp_export_skin.py

# Check 
if [ ! -d $GIMP_PLUGINS_DIR ]; then
    echo "Error : Cannot find Gimp plugins directory, gimp 2.8 is required"
    return 1
fi

install_plugin_file() {
    PLUGIN_FILE=$1
    TARGET_LINK=$GIMP_PLUGINS_DIR/$PLUGIN_FILE

    if [ -L $TARGET_LINK ]; then
        rm $TARGET_LINK
    fi

    ln -s $MY_PLUGINS_DIR/$PLUGIN_FILE $TARGET_LINK
}

# Update links
install_plugin_file "gimp_export_json.py"
install_plugin_file "gimp_export_skin.py"

echo ""
echo "Plugins installed successfully, now you need to restart Gimp"
echo "Enjoy Exporting, Importing emulator skins from File -> Import json, File -> Export skin"

#!/bin/bash
# =========================================================
# Script to create a Debian package for LinSticky
# =========================================================

set -e

PACKAGE_DIR="linsticky_deb"
DEBIAN_DIR="$PACKAGE_DIR/DEBIAN"
USR_BIN_DIR="$PACKAGE_DIR/usr/local/bin"
USR_SHARE_DIR="$PACKAGE_DIR/usr/share"
APPLICATIONS_DIR="$USR_SHARE_DIR/applications"
APP_DIR="$USR_SHARE_DIR/linsticky"
METAINFO_DIR="$USR_SHARE_DIR/metainfo"
APP_INFO_JSON="linsticky/app_info.json"
APP_EXEC="linsticky"
APP_MAIN_SCRIPT="/usr/share/linsticky/main.py"
ICON_PATH="/usr/share/linsticky/resources/icons/app.png"

# ----------------------
# Start from a clean staging directory so files removed from the project
# do not linger in the package
# ----------------------
rm -rf "$PACKAGE_DIR"

# ----------------------
# Create necessary directories if they don't exist
# ----------------------
for dir in "$DEBIAN_DIR" "$USR_BIN_DIR" "$APPLICATIONS_DIR" "$APP_DIR" "$METAINFO_DIR"; do
    [ ! -d "$dir" ] && mkdir -p "$dir"
done

# ----------------------
# Copy all application files to /usr/share/linsticky
# ----------------------
cp -r linsticky/* "$APP_DIR/"
find "$APP_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +

# ----------------------
# Read application info from JSON
# ----------------------
SERVICE_NAME=$(jq -r '.service_name' "$APP_INFO_JSON")
APP_NAME=$(jq -r '.app_name' "$APP_INFO_JSON")
VERSION=$(jq -r '.version' "$APP_INFO_JSON")
DESCRIPTION=$(jq -r '.description' "$APP_INFO_JSON")
AUTHOR=$(jq -r '.author' "$APP_INFO_JSON")
EMAIL=$(jq -r '.email' "$APP_INFO_JSON")
MAINTAINER="$AUTHOR <$EMAIL>"
ARCHITECTURE=$(jq -r '.architecture' "$APP_INFO_JSON")
DEPENDENCIES=$(jq -r '.dependencies | join(", ")' "$APP_INFO_JSON")
WEBSITE=$(jq -r '.website' "$APP_INFO_JSON")
LICENSE=$(jq -r '.license' "$APP_INFO_JSON")

# ----------------------
# Create executable script in /usr/local/bin
# ----------------------
cat > "$USR_BIN_DIR/$APP_EXEC" <<EOL
#!/bin/bash
exec python3 "$APP_MAIN_SCRIPT" "\$@"
EOL
chmod +x "$USR_BIN_DIR/$APP_EXEC"

# ----------------------
# Create DEBIAN/control file
# ----------------------
cat > "$DEBIAN_DIR/control" <<EOL
Package: $SERVICE_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCHITECTURE
Depends: $DEPENDENCIES
Maintainer: $MAINTAINER
Vendor: $AUTHOR
Homepage: $WEBSITE
Description: $DESCRIPTION
EOL

# ----------------------
# Create DEBIAN/postinst to check PyGObject
# ----------------------
cat > "$DEBIAN_DIR/postinst" <<'EOL'
#!/bin/bash
# Check that PyGObject (GTK bindings) is available
if ! python3 -c "import gi" &>/dev/null; then
    echo "Warning: python3-gi is not installed. Please run: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
fi
# The snap and the deb are separate installations with separate launchers.
if command -v snap >/dev/null 2>&1 && snap list linsticky >/dev/null 2>&1; then
    echo "Note: the LinSticky snap is installed too, so two LinSticky launchers will be shown."
    echo "      Keep one of them, e.g.: sudo snap remove linsticky"
fi
exit 0
EOL
chmod +x "$DEBIAN_DIR/postinst"

# ----------------------
# Create desktop entry file
# The file name must equal the application ID (GApplication / Wayland app_id),
# otherwise GNOME cannot match the running window to this launcher: it shows a
# second icon and keeps the launcher "starting" until a timeout.
# ----------------------
DESKTOP_FILE="$APPLICATIONS_DIR/$SERVICE_NAME.desktop"
cat > "$DESKTOP_FILE" <<EOL
[Desktop Entry]
Name=$APP_NAME
Comment=$DESCRIPTION
Exec=/usr/local/bin/$APP_EXEC
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Utility;
StartupNotify=true
# ВАЖНО: StartupWMClass должен СТРОГО совпадать с GLib.set_prgname() в main.py
StartupWMClass=$SERVICE_NAME
EOL

# ----------------------
# Create AppStream metainfo file
# ----------------------
METAINFO_FILE="$METAINFO_DIR/$SERVICE_NAME.metainfo.xml"
cat > "$METAINFO_FILE" <<EOL
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>$SERVICE_NAME</id>
  <launchable type="desktop-id">$SERVICE_NAME.desktop</launchable>
  <metadata_license>CC0-1.0</metadata_license>
  <name>$APP_NAME</name>
  <summary>$DESCRIPTION</summary>
  <developer_name>$AUTHOR</developer_name>
  <description>
    <p>$DESCRIPTION</p>
  </description>
  <url type="homepage">$WEBSITE</url>
  <project_license>$LICENSE</project_license>
</component>
EOL

# ----------------------
# Build the .deb package with flags
# ----------------------
DEB_FILE="${SERVICE_NAME}_${VERSION}_${ARCHITECTURE}.deb"
dpkg-deb --build --root-owner-group --verbose "$PACKAGE_DIR" "$DEB_FILE"

echo ""
echo "Package built successfully: $DEB_FILE"
echo "Installation instructions:"
echo "  sudo dpkg -i $DEB_FILE"
echo "  sudo apt-get install -f  # to install missing dependencies if required"
echo ""
echo "You can launch the application from the menu or by running:"
echo "  $APP_EXEC"

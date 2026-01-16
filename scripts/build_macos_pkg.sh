#!/bin/bash
set -euo pipefail

# Check arguments
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <version> [signing_identity]"
    exit 1
fi

VERSION="$1"
IDENTITY="${2:-}"

# Define paths
DIST_DIR="dist"
BUILD_DIR="build/pkg-root"
APP_DIR="/usr/local/lib/kimi"
BIN_DIR="/usr/local/bin"
PKG_NAME="kimi-${VERSION}-macos-installer.pkg"
PKG_OUTPUT="${DIST_DIR}/${PKG_NAME}"
ONEDIR_SOURCE="${DIST_DIR}/kimi"

echo "==> Preparing to build macOS package for version ${VERSION}"

# Verify onedir build exists
if [ ! -d "${ONEDIR_SOURCE}" ]; then
    echo "Error: Source directory '${ONEDIR_SOURCE}' does not exist."
    echo "Please run 'make build-bin-onedir' first."
    exit 1
fi

# Clean previous build artifacts
rm -rf "${BUILD_DIR}"
rm -f "${PKG_OUTPUT}"

# Create directory structure for the package
# We want to install the app to /usr/local/lib/kimi
# and symlink the binary to /usr/local/bin/kimi
mkdir -p "${BUILD_DIR}${APP_DIR}"
mkdir -p "${BUILD_DIR}${BIN_DIR}"

echo "==> Copying files..."
cp -a "${ONEDIR_SOURCE}/" "${BUILD_DIR}${APP_DIR}/"

echo "==> Creating symlink..."
# Create the symlink in the staging area
# Note: The symlink target is relative to the install location on the user's system
ln -sf "${APP_DIR}/kimi" "${BUILD_DIR}${BIN_DIR}/kimi"

echo "==> Building component package..."

# If identity is provided, sign the package
SIGNING_ARGS=()
if [ -n "${IDENTITY}" ]; then
    echo "==> Will sign package with identity: ${IDENTITY}"
    SIGNING_ARGS=(--sign "${IDENTITY}")
else
    echo "==> No signing identity provided, skipping signature."
fi

# Build the package
# --root: The staging directory containing the file structure
# --identifier: Bundle identifier
# --version: Package version
# --install-location: Where to install the root content (we use / to map our structure absolutely)
pkgbuild \
    --root "${BUILD_DIR}" \
    --identifier "com.moonshot.kimi.cli" \
    --version "${VERSION}" \
    --install-location "/" \
    "${SIGNING_ARGS[@]}" \
    "${PKG_OUTPUT}"

echo "==> Package built successfully at: ${PKG_OUTPUT}"

# Executable Artifacts

This directory is reserved for launch helpers and self-contained binaries built from the BEMU (Byte Emu) tools.

* `launch.sh` – Bash wrapper that starts the Tkinter-based GUI VM manager.  The script replaces the previously distributed AppImage
  and simply proxies through to ``tools/gui_vm_manager.py`` so contributors can launch the manager without rebuilding an AppImage.
  It respects the same ``$BEMU_BINARY`` and command-line overrides exposed by the Python entry point.
* `BEMU_VM_Manager-x86_64.AppImage` – Optional AppImage for the GUI VM manager.  The binary is no longer checked into the
  repository so contributors can send pull requests without tripping binary-upload restrictions, but locally-built copies may still
  be placed here if you prefer the AppImage packaging.  The bundle includes shortcuts for the virtual-display-rs driver, Virtual
  Audio Driver, the V4004 CPU reference implementation, pintOS Virtual Memory, and Apple's open-source ``dyld`` tree for running
  macOS-family guests.  The firmware bundle ships the ``bios.bin`` image from `coreboot/seabios <https://github.com/coreboot/seabios>`_,
  so the packaged manager can boot guests without any additional BIOS downloads.

## launch.sh helper

To launch the GUI manager without building an AppImage, run:

```bash
./executable/launch.sh
```

The script defaults to ``python3`` but honours ``$PYTHON`` if you need to point at an alternate interpreter (for example a virtual
environment).

## Rebuilding the AppImage

If you still want to produce an AppImage from a clean checkout:

```bash
sudo apt-get update && sudo apt-get install -y file
python3 -m venv build/AppDir/usr
install -Dm755 tools/gui_vm_manager.py build/AppDir/usr/bin/gui_vm_manager.py
cat <<'EOR' > build/AppDir/AppRun
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONHOME="$HERE/usr"
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/bin/python3" "$HERE/usr/bin/gui_vm_manager.py" "$@"
EOR
chmod +x build/AppDir/AppRun
cat <<'EOD' > build/AppDir/gui-vm-manager.desktop
[Desktop Entry]
Type=Application
Name=BEMU VM Manager
Exec=AppRun
Icon=gui-vm-manager
Categories=Utility;System;
Terminal=false
EOD
cat <<'EOS' > build/AppDir/gui-vm-manager.svg
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="48" ry="48" fill="#1b73ba"/>
  <g fill="#ffffff" font-family="sans-serif" font-weight="bold" text-anchor="middle">
    <text x="128" y="120" font-size="72">VM</text>
    <text x="128" y="190" font-size="48">GUI</text>
  </g>
</svg>
EOS
install -Dm644 build/AppDir/gui-vm-manager.svg build/AppDir/usr/share/icons/hicolor/scalable/apps/gui-vm-manager.svg
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 ./appimagetool-x86_64.AppImage build/AppDir
mv AppDir-x86_64.AppImage BEMU_VM_Manager-x86_64.AppImage
mv BEMU_VM_Manager-x86_64.AppImage executable/
```

The build steps use only system Python and the AppImageKit tooling so no additional Python dependencies are required.

VMX configuration files are supported directly in the GUI; when a ``.vmx`` file is chosen, the launcher extracts the referenced
disk image and resource defaults so the generated AppImage offers parity with VMware-based guest descriptors.

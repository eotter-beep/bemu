.. _gui_vm_manager:

========================
BEMU GUI VM Manager
========================

The ``gui_vm_manager.py`` helper in :file:`tools/` provides a lightweight
Tkinter based front-end for launching BEMU (Byte Emu) VMs without manually
crafting long command lines.  The utility focuses on a few common configuration
knobs and ships alongside the normal BEMU tooling so it can be used without
additional Python dependencies.

Launching the manager
---------------------

.. code-block:: bash

   $ python3 tools/gui_vm_manager.py

The window exposes the following inputs:

* **BEMU binary** – the Byte Emu system emulator to invoke.  Relative names
  (for example ``qemu-system-x86_64``) resolve through ``$PATH`` while absolute
  paths are validated before launch.  Set ``$BEMU_BINARY`` to override the
  default executable.
* **Disk image** – optional disk image to attach either with a VirtIO drive
  (``.qcow2`` images) or a legacy ``-hda`` attachment for raw files.  The dialog
  also accepts VMware ``.vmx`` configurations; when selected, the manager reads
  the file to pull out the referenced disk, memory, and vCPU settings so the
  BEMU launch matches the VMX defaults where possible.
* **Memory (MB)** and **vCPUs** – resource allocations for the guest.  Values
  are validated to avoid launching VMs with nonsensical parameters.
* **CPU Model** – defaults to the `V4004 virtual CPU <https://github.com/a4004/v4004cpu>`_
  and is passed through ``-cpu`` when the VM starts.
* **Machine** – the machine type passed to ``-machine`` (defaults to ``q35``).
* **SeaBIOS firmware** – optional BIOS passed through ``-bios``.

The interface now allows free resizing, including maximizing the window.  The
fields expand horizontally so wider layouts expose more of each path without
requiring horizontal scrolling, and additional vertical space is absorbed by
the status area to keep the controls readable on large displays.

SeaBIOS integration
-------------------

The GUI looks for a SeaBIOS image (``bios.bin``) in a few common locations,
starting with the copy that ships in :file:`pc-bios/` and then falling back to
``$SEABIOS_DIR`` and the usual system paths.  The bundled image is tracked from
`coreboot/seabios <https://github.com/coreboot/seabios>`_ so freshly cloned
trees already contain a working BIOS without any extra downloads.  The
**SeaBIOS Repository** button opens that upstream project if you want to review
the source or pull a newer build.

Runtime resources
-----------------

Windows guests can install the `virtual-display-rs driver
<https://github.com/MolotovCherry/virtual-display-rs>`_ straight from the
manager via the dedicated button.  The driver improves integration for BEMU's
virtual GPU pipeline on Linux and Windows alike and keeps the guest display
responsive when toggling fullscreen modes with :kbd:`Ctrl` + :kbd:`O`.  An
additional shortcut points to the `Virtual Audio Driver <https://github.com/VirtualDrivers/Virtual-Audio-Driver>`_
so BEMU users can pair display and audio integration within the same workflow.

The GUI also provides shortcuts to the projects that inform the default BEMU
experience.  The `V4004 CPU project <https://github.com/a4004/v4004cpu>`_
documents the CPU model pre-selected in the launcher, while
`pintOS Virtual Memory <https://github.com/davidpeterko/pintOS-Virtual-Memory>`_
explains the paging approach that guides the manager's memory defaults.  For
Apple guests, the **Apple dyld Loader** button opens the
`open-source dyld tree <https://github.com/apple-opensource/dyld>`_ so users can
fetch dynamic loader support suitable for macOS and other Apple operating
systems.

Manual usage
------------

The manager maintains a minimal process lifecycle: it spawns BEMU on *Start*,
monitors the subprocess to keep the status label up-to-date, and sends
``SIGINT`` when *Stop* is pressed.  If the process does not terminate, it falls
back to ``SIGTERM``.  This mirrors the behaviour of stopping a VM from a
terminal while providing a friendly GUI wrapper.

Launch helpers
--------------

The repository now ships :file:`executable/launch.sh`, a Bash wrapper that
invokes :file:`tools/gui_vm_manager.py` with your preferred interpreter (set
``$PYTHON`` to override the default ``python3``).  This replaces the old
AppImage workflow while keeping launch instructions as simple as:

.. code-block:: bash

   $ ./executable/launch.sh

If you still prefer the AppImage format, rebuild it by following the steps in
:file:`executable/README.md` and drop the resulting
``BEMU_VM_Manager-x86_64.AppImage`` into :file:`executable/`.  The directory is
already ignored for ``*.AppImage`` artifacts so local builds will not affect
pull requests.

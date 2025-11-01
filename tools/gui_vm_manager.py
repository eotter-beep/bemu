#!/usr/bin/env python3
"""Simple Tkinter-based GUI VM manager for launching BEMU (Byte Emu) VMs.

This tool gives a quick way to launch and manage BEMU virtual machines without
needing to remember long command lines.  It focuses on common host-side
controls like starting/stopping the VM, adjusting resource allocations, and
selecting firmware images.  The interface intentionally keeps the dependency
footprint small so it can ship alongside the existing BEMU tools.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional


DEFAULT_MEMORY = 2048
DEFAULT_CPU_COUNT = 2
DEFAULT_CPU_NAME = "v4004"
DEFAULT_BIOS_NAME = "bios.bin"
AUDIO_DRIVER_URL = "https://github.com/VirtualDrivers/Virtual-Audio-Driver"
DISPLAY_DRIVER_URL = "https://github.com/MolotovCherry/virtual-display-rs"
CPU_REPO_URL = "https://github.com/a4004/v4004cpu"
MEMORY_REPO_URL = "https://github.com/davidpeterko/pintOS-Virtual-Memory"
DYLD_REPO_URL = "https://github.com/apple-opensource/dyld"
SEABIOS_REPO_URL = "https://github.com/coreboot/seabios"
DEFAULT_BIOS_DIRS = (
    Path(__file__).resolve().parent.parent / "pc-bios",
    Path(os.environ.get("SEABIOS_DIR", "")),
    Path.home() / ".local" / "share" / "seabios",
    Path("/usr/share/seabios"),
    Path("/usr/local/share/seabios"),
)
DEFAULT_MACHINE = "q35"


def _parse_vmx_file(vmx_path: Path) -> dict[str, str | Path]:
    """Parse a minimal subset of a VMware VMX file."""

    data: dict[str, str | Path] = {}
    disk_path: Optional[Path] = None
    try:
        with vmx_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"')
                lowered_key = key.lower()
                if lowered_key == "memsize":
                    data["memsize"] = value
                elif lowered_key == "numvcpus":
                    data["numvcpus"] = value
                elif key.endswith(".fileName") and value:
                    candidate = Path(value)
                    if not candidate.is_absolute():
                        candidate = (vmx_path.parent / candidate).resolve()
                    if (
                        candidate.suffix.lower() in {".vmdk", ".qcow2", ".img", ".raw"}
                        and candidate.exists()
                    ):
                        disk_path = candidate
                        break
    except (OSError, UnicodeDecodeError):
        return data

    if disk_path:
        data["disk"] = disk_path
    return data


def _find_default_bios() -> Optional[Path]:
    """Search for a SeaBIOS image in common locations."""

    for directory in DEFAULT_BIOS_DIRS:
        if not directory:
            continue
        candidate = directory / DEFAULT_BIOS_NAME
        if candidate.is_file():
            return candidate
    return None


@dataclass
class VMConfig:
    binary: Path
    disk_image: Optional[Path]
    memory_mb: int
    cpu_count: int
    cpu_model: str
    bios: Optional[Path]
    machine: str

    def build_command(self) -> list[str]:
        cmd = [
            str(self.binary),
            "-machine",
            self.machine,
            "-m",
            str(self.memory_mb),
            "-smp",
            str(self.cpu_count),
            "-cpu",
            self.cpu_model,
        ]
        if self.bios:
            cmd.extend(["-bios", str(self.bios)])
        if self.disk_image:
            if self.disk_image.suffix == '.qcow2':
                cmd.extend(['-drive', f'file={self.disk_image},if=virtio,format=qcow2'])
            else:
                cmd.extend(['-hda', str(self.disk_image)])
        return cmd


class VMManager(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BEMU VM Manager")
        self.geometry("640x320")
        self.resizable(False, False)

        self._vm_process: Optional[subprocess.Popen[str]] = None
        self._stop_event = threading.Event()

        self._create_widgets()
        self._populate_defaults()

    # ------------------------------------------------------------------
    # UI helpers
    def _create_widgets(self) -> None:
        padding = {"padx": 10, "pady": 5}
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # BEMU binary
        ttk.Label(main_frame, text="BEMU Binary").grid(row=0, column=0, sticky=tk.W, **padding)
        self.binary_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.binary_var, width=50).grid(
            row=0, column=1, sticky=tk.EW, **padding
        )
        ttk.Button(main_frame, text="Browse", command=self._choose_binary).grid(
            row=0, column=2, sticky=tk.E, **padding
        )

        # Disk image
        ttk.Label(main_frame, text="Disk Image").grid(row=1, column=0, sticky=tk.W, **padding)
        self.disk_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.disk_var, width=50).grid(
            row=1, column=1, sticky=tk.EW, **padding
        )
        ttk.Button(main_frame, text="Browse", command=self._choose_disk).grid(
            row=1, column=2, sticky=tk.E, **padding
        )

        # Memory
        ttk.Label(main_frame, text="Memory (MB)").grid(row=2, column=0, sticky=tk.W, **padding)
        self.memory_var = tk.IntVar(value=DEFAULT_MEMORY)
        ttk.Spinbox(main_frame, from_=256, to=262144, textvariable=self.memory_var, increment=256).grid(
            row=2, column=1, sticky=tk.W, **padding
        )

        # CPUs
        ttk.Label(main_frame, text="vCPUs").grid(row=3, column=0, sticky=tk.W, **padding)
        self.cpus_var = tk.IntVar(value=DEFAULT_CPU_COUNT)
        ttk.Spinbox(main_frame, from_=1, to=os.cpu_count() or 16, textvariable=self.cpus_var).grid(
            row=3, column=1, sticky=tk.W, **padding
        )

        # CPU model
        ttk.Label(main_frame, text="CPU Model").grid(row=4, column=0, sticky=tk.W, **padding)
        self.cpu_model_var = tk.StringVar(value=DEFAULT_CPU_NAME)
        ttk.Entry(main_frame, textvariable=self.cpu_model_var).grid(
            row=4, column=1, sticky=tk.W, **padding
        )

        # Machine type
        ttk.Label(main_frame, text="Machine").grid(row=5, column=0, sticky=tk.W, **padding)
        self.machine_var = tk.StringVar(value=DEFAULT_MACHINE)
        ttk.Entry(main_frame, textvariable=self.machine_var).grid(row=5, column=1, sticky=tk.W, **padding)

        # BIOS path
        ttk.Label(main_frame, text="SeaBIOS Firmware").grid(row=6, column=0, sticky=tk.W, **padding)
        self.bios_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.bios_var, width=50).grid(
            row=6, column=1, sticky=tk.EW, **padding
        )
        ttk.Button(main_frame, text="Browse", command=self._choose_bios).grid(
            row=6, column=2, sticky=tk.E, **padding
        )
        ttk.Button(
            main_frame,
            text="SeaBIOS Repository",
            command=self._open_seabios_repo,
        ).grid(
            row=7, column=2, sticky=tk.E, **padding
        )

        ttk.Button(
            main_frame,
            text="virtual-display-rs Driver",
            command=self._open_display_driver_repo,
        ).grid(row=8, column=2, sticky=tk.E, **padding)

        ttk.Button(
            main_frame,
            text="Virtual Audio Driver",
            command=self._open_audio_driver_repo,
        ).grid(row=9, column=2, sticky=tk.E, **padding)

        ttk.Button(
            main_frame,
            text="V4004 CPU Project",
            command=self._open_cpu_repo,
        ).grid(row=10, column=2, sticky=tk.E, **padding)

        ttk.Button(
            main_frame,
            text="pintOS Virtual Memory",
            command=self._open_memory_repo,
        ).grid(row=11, column=2, sticky=tk.E, **padding)

        ttk.Button(
            main_frame,
            text="Apple dyld Loader",
            command=self._open_dyld_repo,
        ).grid(row=12, column=2, sticky=tk.E, **padding)

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var).grid(row=13, column=0, columnspan=2, sticky=tk.W, **padding)

        # Control buttons
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=14, column=0, columnspan=3, sticky=tk.E, **padding)
        ttk.Button(control_frame, text="Start VM", command=self.start_vm).grid(row=0, column=0, padx=5)
        ttk.Button(control_frame, text="Stop VM", command=self.stop_vm).grid(row=0, column=1, padx=5)

        main_frame.columnconfigure(1, weight=1)

    def _populate_defaults(self) -> None:
        default_binary = os.environ.get(
            "BEMU_BINARY",
            os.environ.get("QEMU_BINARY", "qemu-system-x86_64"),
        )
        self.binary_var.set(default_binary)
        bios_path = _find_default_bios()
        if bios_path:
            self.bios_var.set(str(bios_path))
        self.cpu_model_var.set(DEFAULT_CPU_NAME)

    # ------------------------------------------------------------------
    # Event handlers
    def _choose_binary(self) -> None:
        selected = filedialog.askopenfilename(title="Select BEMU binary")
        if selected:
            self.binary_var.set(selected)

    def _choose_disk(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select disk image or VMX configuration",
            filetypes=[
                ("Disk or VMX", "*.qcow2 *.img *.raw *.vmdk *.vmx"),
                ("All files", "*"),
            ],
        )
        if selected:
            path = Path(selected)
            if path.suffix.lower() == ".vmx":
                self._apply_vmx_config(path)
            else:
                self.disk_var.set(selected)
                self.status_var.set("Ready")

    def _choose_bios(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select SeaBIOS Image",
            filetypes=[("BIOS images", "*.bin *.rom"), ("All files", "*")],
        )
        if selected:
            self.bios_var.set(selected)

    def _open_seabios_repo(self) -> None:
        import webbrowser

        webbrowser.open(SEABIOS_REPO_URL, new=2)

    def _open_display_driver_repo(self) -> None:
        import webbrowser

        webbrowser.open(DISPLAY_DRIVER_URL, new=2)

    def _open_audio_driver_repo(self) -> None:
        import webbrowser

        webbrowser.open(AUDIO_DRIVER_URL, new=2)

    def _open_cpu_repo(self) -> None:
        import webbrowser

        webbrowser.open(CPU_REPO_URL, new=2)

    def _open_memory_repo(self) -> None:
        import webbrowser

        webbrowser.open(MEMORY_REPO_URL, new=2)

    def _open_dyld_repo(self) -> None:
        import webbrowser

        webbrowser.open(DYLD_REPO_URL, new=2)

    def _apply_vmx_config(self, vmx_path: Path) -> None:
        vmx_data = _parse_vmx_file(vmx_path)
        disk = vmx_data.get("disk")
        if disk:
            self.disk_var.set(str(disk))
        else:
            # Fall back to storing the VMX path to let QEMU error if unsupported
            self.disk_var.set(str(vmx_path))

        if "memsize" in vmx_data:
            try:
                self.memory_var.set(int(vmx_data["memsize"]))
            except (ValueError, tk.TclError):
                pass

        if "numvcpus" in vmx_data:
            try:
                self.cpus_var.set(int(vmx_data["numvcpus"]))
            except (ValueError, tk.TclError):
                pass

        status_details = []
        if disk:
            status_details.append(f"disk: {disk.name}")
        if "memsize" in vmx_data:
            status_details.append(f"memory: {vmx_data['memsize']} MB")
        if "numvcpus" in vmx_data:
            status_details.append(f"vCPUs: {vmx_data['numvcpus']}")
        if status_details:
            self.status_var.set("Loaded VMX (" + ", ".join(status_details) + ")")
        else:
            self.status_var.set("Loaded VMX configuration")

    # ------------------------------------------------------------------
    # VM lifecycle management
    def _build_config(self) -> Optional[VMConfig]:
        try:
            memory_mb = int(self.memory_var.get())
            cpus = int(self.cpus_var.get())
        except (TypeError, tk.TclError, ValueError):
            messagebox.showerror("Invalid Configuration", "Memory and CPU counts must be integers")
            return None

        binary_value = self.binary_var.get().strip()
        if not binary_value:
            messagebox.showerror("Invalid Configuration", "Please choose a BEMU binary")
            return None

        binary = Path(binary_value).expanduser()
        has_path_sep = os.sep in binary_value or (os.altsep and os.altsep in binary_value)
        if has_path_sep and not binary.exists():
            messagebox.showerror("Invalid Configuration", f"BEMU binary '{binary}' does not exist")
            return None

        disk = Path(self.disk_var.get()).expanduser() if self.disk_var.get() else None
        if disk and not disk.exists():
            messagebox.showerror("Invalid Disk", f"Disk image '{disk}' does not exist")
            return None

        bios = Path(self.bios_var.get()).expanduser() if self.bios_var.get() else None
        if bios and not bios.exists():
            messagebox.showerror("Invalid BIOS", f"SeaBIOS image '{bios}' was not found")
            return None

        return VMConfig(
            binary=binary,
            disk_image=disk if disk else None,
            memory_mb=memory_mb,
            cpu_count=cpus,
            cpu_model=self.cpu_model_var.get().strip() or DEFAULT_CPU_NAME,
            bios=bios,
            machine=self.machine_var.get() or DEFAULT_MACHINE,
        )

    def start_vm(self) -> None:
        if self._vm_process and self._vm_process.poll() is None:
            messagebox.showinfo("VM Running", "The VM is already running")
            return

        config = self._build_config()
        if not config:
            return

        command = config.build_command()
        self.status_var.set("Starting VM...")
        try:
            self._vm_process = subprocess.Popen(command)
            self._stop_event.clear()
            self.status_var.set("VM running")
            threading.Thread(target=self._monitor_process, daemon=True).start()
        except FileNotFoundError:
            messagebox.showerror("Launch Failed", f"Could not find executable '{config.binary}'")
            self.status_var.set("Launch failed")
        except Exception as exc:  # pylint: disable=broad-except
            messagebox.showerror("Launch Failed", f"Failed to launch VM: {exc}")
            self.status_var.set("Launch failed")

    def stop_vm(self) -> None:
        if not self._vm_process or self._vm_process.poll() is not None:
            self.status_var.set("No VM running")
            return

        self.status_var.set("Stopping VM...")
        self._stop_event.set()
        try:
            self._vm_process.send_signal(signal.SIGINT)
        except Exception:  # pylint: disable=broad-except
            self._vm_process.terminate()
        finally:
            self.after(100, self._finalize_stop)

    def _monitor_process(self) -> None:
        if not self._vm_process:
            return
        self._vm_process.wait()
        if not self._stop_event.is_set():
            self.status_var.set("VM exited")
        else:
            self.status_var.set("VM stopped")

    def _finalize_stop(self) -> None:
        if self._vm_process and self._vm_process.poll() is None:
            self.after(100, self._finalize_stop)
            return
        self.status_var.set("VM stopped")


def main() -> int:
    app = VMManager()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

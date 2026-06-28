"""
app_window.py — Cửa sổ chính của ứng dụng Linux System Manager.
Chứa Gtk.Notebook với 4 tab, thanh trạng thái, và nút toggle Dark/Light mode.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from gui.tab_process import TabProcess
from gui.tab_file import TabFile
from gui.tab_socket import TabSocket
from gui.tab_network import TabNetwork


class AppWindow(Gtk.Window):
    """
    Cửa sổ chính — chứa notebook 4 tab, status bar, và dark/light toggle.
    Kích thước tối thiểu: 900 × 650 px.
    """

    def __init__(self) -> None:
        # Ensure GTK prefers light theme BEFORE window initialization
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", False)

        super().__init__(title="Linux System Manager")
        self.set_default_size(1050, 750)
        self.set_size_request(900, 650)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._dark_mode = False

        # Container chính
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Notebook (tabs)
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        vbox.pack_start(self.notebook, True, True, 0)

        # Khởi tạo 4 tab
        self.tab_process = TabProcess()
        self.tab_file = TabFile()
        self.tab_socket = TabSocket()
        self.tab_network = TabNetwork()

        # Thêm tab với label
        self.notebook.append_page(self.tab_process, Gtk.Label(label="Process Manager"))
        self.notebook.append_page(self.tab_file, Gtk.Label(label="File"))
        self.notebook.append_page(self.tab_socket, Gtk.Label(label="Socket"))
        self.notebook.append_page(self.tab_network, Gtk.Label(label="Network"))

        # Thanh trạng thái (statusbar)
        statusbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        statusbar_box.get_style_context().add_class("statusbar")
        vbox.pack_end(statusbar_box, False, False, 0)

        self.statusbar_label = Gtk.Label(label="Trạng thái: Sẵn sàng")
        self.statusbar_label.set_halign(Gtk.Align.START)
        self.statusbar_label.set_hexpand(True)
        statusbar_box.pack_start(self.statusbar_label, True, True, 0)

        # Version
        version_label = Gtk.Label(label="v2.0.0")
        version_label.get_style_context().add_class("metadata-label")
        statusbar_box.pack_start(version_label, False, False, 8)

        # System Stats
        self.sys_stats_label = Gtk.Label(label="CPU: --% | RAM: --%")
        self.sys_stats_label.get_style_context().add_class("metadata-label")
        statusbar_box.pack_start(self.sys_stats_label, False, False, 16)

        # Nút toggle Dark/Light mode
        self.btn_mode = Gtk.Button(label="Dark Mode")
        self.btn_mode.get_style_context().add_class("mode-toggle")
        self.btn_mode.connect("clicked", self._on_toggle_mode)
        statusbar_box.pack_end(self.btn_mode, False, False, 4)

        # Xử lý đóng cửa sổ — cleanup tất cả subprocess
        self.connect("destroy", self._on_destroy)

        # Bắt đầu timer cập nhật CPU/RAM
        GLib.timeout_add(2000, self._update_system_stats)

    def _update_system_stats(self) -> bool:
        """Đọc /proc/stat và /proc/meminfo để hiển thị tổng quan %CPU và %RAM."""
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            mem_total = mem_avail = 0
            for line in lines:
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    mem_avail = int(line.split()[1])
            mem_percent = ((mem_total - mem_avail) / mem_total * 100) if mem_total else 0
            
            with open('/proc/stat', 'r') as f:
                cpu_line = f.readline()
            parts = [int(p) for p in cpu_line.split()[1:]]
            idle = parts[3]
            total = sum(parts)
            
            if hasattr(self, '_last_cpu_total'):
                diff_total = total - self._last_cpu_total
                diff_idle = idle - self._last_cpu_idle
                cpu_percent = (diff_total - diff_idle) / diff_total * 100 if diff_total else 0
            else:
                cpu_percent = 0
                
            self._last_cpu_total = total
            self._last_cpu_idle = idle
            
            self.sys_stats_label.set_text(f"CPU: {cpu_percent:.1f}% | RAM: {mem_percent:.1f}%")
        except Exception:
            self.sys_stats_label.set_text("CPU/RAM: N/A")
            
        return True # Giữ timer tiếp tục chạy

    def update_status(self, msg: str) -> None:
        """Cập nhật nội dung thanh trạng thái từ các tab con."""
        self.statusbar_label.set_text(f"Trạng thái: {msg}")

    def _on_toggle_mode(self, button: Gtk.Button) -> None:
        """Toggle Dark/Light mode bằng cách thêm/bỏ CSS class 'dark-mode' trên window."""
        self._dark_mode = not self._dark_mode
        style_ctx = self.get_style_context()
        settings = Gtk.Settings.get_default()

        if self._dark_mode:
            style_ctx.add_class("dark-mode")
            if settings:
                settings.set_property("gtk-application-prefer-dark-theme", True)
            self.btn_mode.set_label("Light Mode")
        else:
            style_ctx.remove_class("dark-mode")
            if settings:
                settings.set_property("gtk-application-prefer-dark-theme", False)
            self.btn_mode.set_label("Dark Mode")

    def _on_destroy(self, widget: Gtk.Widget) -> None:
        """Cleanup khi đóng cửa sổ: dừng tất cả subprocess và timer."""
        # Dừng tab process (timer auto-refresh)
        if hasattr(self.tab_process, 'cleanup'):
            self.tab_process.cleanup()
        # Dừng tab file (inotify subprocess)
        if hasattr(self.tab_file, 'cleanup'):
            self.tab_file.cleanup()
        # Dừng tab socket (server/client subprocess)
        if hasattr(self.tab_socket, 'cleanup'):
            self.tab_socket.cleanup()
        # Dừng tab network (ping subprocess)
        if hasattr(self.tab_network, 'cleanup'):
            self.tab_network.cleanup()

"""
app_window.py — Cửa sổ chính của ứng dụng Linux System Manager.
Chứa Gtk.Notebook với 4 tab, thanh trạng thái, và nút toggle Dark/Light mode.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

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
        self.notebook.append_page(self.tab_file, Gtk.Label(label="File I/O"))
        self.notebook.append_page(self.tab_socket, Gtk.Label(label="Socket TCP"))
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

        # Nút toggle Dark/Light mode
        self.btn_mode = Gtk.Button(label="Dark Mode")
        self.btn_mode.get_style_context().add_class("mode-toggle")
        self.btn_mode.connect("clicked", self._on_toggle_mode)
        statusbar_box.pack_end(self.btn_mode, False, False, 4)

        # Xử lý đóng cửa sổ — cleanup tất cả subprocess
        self.connect("destroy", self._on_destroy)

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

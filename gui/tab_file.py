"""
tab_file.py — Tab quản lý File I/O + inotify + Permissions.
Sub-tabs: Đọc/Ghi, Theo dõi (inotify), Quyền & Sở hữu.
Tự động đọc file khi chọn, chế độ append/overwrite, mmap inline.
"""

import os
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from utils.helpers import get_backend_path, format_bytes, format_datetime, format_permissions


class TabFile(Gtk.Box):
    """
    Tab File I/O — chia thành 3 sub-tabs:
    - Đọc/Ghi: chọn file, auto-read, text + hex, write (append/overwrite), mmap
    - Theo dõi (inotify): chọn file/folder, watch real-time
    - Quyền & Sở hữu: hiển thị & thay đổi permissions, owner, group
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_border_width(12)

        self._backend = get_backend_path("file_mgr")
        self._inotify_proc = None
        self._inotify_thread = None
        self._selected_file = ""

        self._build_ui()

    def _build_ui(self) -> None:
        """Xây dựng giao diện tab File I/O với sub-tabs."""

        self.sub_notebook = Gtk.Notebook()
        self.pack_start(self.sub_notebook, True, True, 0)

        # Sub-tab 1: Đọc/Ghi
        self._build_read_write_tab()
        # Sub-tab 2: Theo dõi (inotify)
        self._build_inotify_tab()
        # Sub-tab 3: Quyền & Sở hữu
        self._build_permissions_tab()

    # ═══════════════════════════════════════════════════════════
    # SUB-TAB 1: Đọc/Ghi
    # ═══════════════════════════════════════════════════════════

    def _build_read_write_tab(self) -> None:
        """Sub-tab đọc/ghi file."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_border_width(8)

        # === Row 1: Chọn file (auto-read) ===
        row_file = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(row_file, False, False, 0)

        row_file.pack_start(Gtk.Label(label="File:"), False, False, 0)
        self.entry_file = Gtk.Entry()
        self.entry_file.set_placeholder_text("/đường/dẫn/tới/file")
        self.entry_file.set_hexpand(True)
        self.entry_file.connect("activate", self._on_entry_file_activate)
        row_file.pack_start(self.entry_file, True, True, 0)

        btn_choose = Gtk.Button(label="Chọn file")
        btn_choose.get_style_context().add_class("btn-primary")
        btn_choose.connect("clicked", self._on_choose_file)
        row_file.pack_start(btn_choose, False, False, 0)

        # === Row 2: Metadata ===
        self.lbl_metadata = Gtk.Label(label="Size: —  |  Quyền: —  |  Sửa: —")
        self.lbl_metadata.set_halign(Gtk.Align.START)
        self.lbl_metadata.get_style_context().add_class("metadata-label")
        self.lbl_metadata.set_margin_bottom(4)
        vbox.pack_start(self.lbl_metadata, False, False, 0)

        # === Paned: Text view | Hex dump ===
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(420)
        vbox.pack_start(paned, True, True, 0)

        # Text view (bên trái)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl_text = Gtk.Label(label="Nội dung (text)")
        lbl_text.get_style_context().add_class("section-label")
        text_box.pack_start(lbl_text, False, False, 0)
        scroll_text = Gtk.ScrolledWindow()
        scroll_text.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.get_style_context().add_class("text-view")
        scroll_text.add(self.text_view)
        text_box.pack_start(scroll_text, True, True, 0)
        paned.pack1(text_box, True, True)

        # Hex dump (bên phải)
        hex_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl_hex = Gtk.Label(label="Hex dump")
        lbl_hex.get_style_context().add_class("section-label")
        hex_box.pack_start(lbl_hex, False, False, 0)
        scroll_hex = Gtk.ScrolledWindow()
        scroll_hex.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.hex_view = Gtk.TextView()
        self.hex_view.set_editable(False)
        self.hex_view.set_monospace(True)
        self.hex_view.get_style_context().add_class("hex-view")
        scroll_hex.add(self.hex_view)
        hex_box.pack_start(scroll_hex, True, True, 0)
        paned.pack2(hex_box, True, True)

        # === Ghi file ===
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(sep1, False, False, 4)

        write_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(write_header, False, False, 0)

        lbl_write = Gtk.Label(label="Ghi vào file:")
        lbl_write.get_style_context().add_class("section-label")
        write_header.pack_start(lbl_write, False, False, 0)

        # Chế độ ghi: Overwrite / Append
        write_header.pack_start(Gtk.Label(label="Chế độ:"), False, False, 4)
        self.combo_write_mode = Gtk.ComboBoxText()
        self.combo_write_mode.append_text("Ghi đè (Overwrite)")
        self.combo_write_mode.append_text("Ghi thêm (Append)")
        self.combo_write_mode.set_active(0)
        write_header.pack_start(self.combo_write_mode, False, False, 0)

        row_write = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vbox.pack_start(row_write, False, False, 0)

        scroll_write = Gtk.ScrolledWindow()
        scroll_write.set_size_request(-1, 60)
        scroll_write.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.write_view = Gtk.TextView()
        self.write_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll_write.add(self.write_view)
        row_write.pack_start(scroll_write, True, True, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row_write.pack_start(btn_box, False, False, 0)

        btn_write = Gtk.Button(label="Ghi file")
        btn_write.get_style_context().add_class("btn-primary")
        btn_write.connect("clicked", self._on_write_file)
        btn_box.pack_start(btn_write, False, False, 0)

        btn_mmap = Gtk.Button(label="mmap demo")
        btn_mmap.connect("clicked", self._on_mmap_demo)
        btn_box.pack_start(btn_mmap, False, False, 0)

        # mmap result inline label
        self.lbl_mmap_result = Gtk.Label(label="")
        self.lbl_mmap_result.set_halign(Gtk.Align.START)
        self.lbl_mmap_result.get_style_context().add_class("mmap-result")
        self.lbl_mmap_result.set_no_show_all(True)
        vbox.pack_start(self.lbl_mmap_result, False, False, 0)

        self.sub_notebook.append_page(vbox, Gtk.Label(label="Đọc/Ghi"))

    # ═══════════════════════════════════════════════════════════
    # SUB-TAB 2: Theo dõi (inotify)
    # ═══════════════════════════════════════════════════════════

    def _build_inotify_tab(self) -> None:
        """Sub-tab theo dõi thay đổi file/folder real-time."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_border_width(8)

        lbl_title = Gtk.Label(label="inotify — Theo dõi thay đổi file/thư mục real-time")
        lbl_title.get_style_context().add_class("section-label")
        lbl_title.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl_title, False, False, 0)

        # Chọn file/folder
        row_watch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(row_watch, False, False, 0)

        row_watch.pack_start(Gtk.Label(label="Đường dẫn:"), False, False, 0)
        self.entry_watch = Gtk.Entry()
        self.entry_watch.set_placeholder_text("Chọn file hoặc thư mục cần theo dõi...")
        self.entry_watch.set_hexpand(True)
        row_watch.pack_start(self.entry_watch, True, True, 0)

        btn_choose_watch_file = Gtk.Button(label="Chọn file")
        btn_choose_watch_file.connect("clicked", self._on_choose_watch_file)
        row_watch.pack_start(btn_choose_watch_file, False, False, 0)

        btn_choose_watch_folder = Gtk.Button(label="Chọn thư mục")
        btn_choose_watch_folder.connect("clicked", self._on_choose_watch_folder)
        row_watch.pack_start(btn_choose_watch_folder, False, False, 0)

        # Nút điều khiển
        row_ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(row_ctrl, False, False, 0)

        self.btn_start_watch = Gtk.Button(label="Bắt đầu theo dõi")
        self.btn_start_watch.get_style_context().add_class("btn-success")
        self.btn_start_watch.connect("clicked", self._on_start_watch)
        row_ctrl.pack_start(self.btn_start_watch, False, False, 0)

        self.btn_stop_watch = Gtk.Button(label="Dừng")
        self.btn_stop_watch.get_style_context().add_class("btn-danger")
        self.btn_stop_watch.connect("clicked", self._on_stop_watch)
        row_ctrl.pack_start(self.btn_stop_watch, False, False, 0)

        self.lbl_watch_status = Gtk.Label(label="Chưa theo dõi")
        self.lbl_watch_status.get_style_context().add_class("metadata-label")
        row_ctrl.pack_start(self.lbl_watch_status, False, False, 8)

        # inotify log
        scroll_inotify = Gtk.ScrolledWindow()
        scroll_inotify.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_inotify.get_style_context().add_class("inotify-log")
        self.inotify_view = Gtk.TextView()
        self.inotify_view.set_editable(False)
        self.inotify_view.set_monospace(True)
        scroll_inotify.add(self.inotify_view)
        vbox.pack_start(scroll_inotify, True, True, 0)

        self.sub_notebook.append_page(vbox, Gtk.Label(label="Theo dõi"))

    # ═══════════════════════════════════════════════════════════
    # SUB-TAB 3: Quyền & Sở hữu
    # ═══════════════════════════════════════════════════════════

    def _build_permissions_tab(self) -> None:
        """Sub-tab quản lý quyền và sở hữu file."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_border_width(8)

        lbl_title = Gtk.Label(label="Quyền & Sở hữu file")
        lbl_title.get_style_context().add_class("section-label")
        lbl_title.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl_title, False, False, 0)

        # Chọn file
        row_file = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(row_file, False, False, 0)

        row_file.pack_start(Gtk.Label(label="File:"), False, False, 0)
        self.entry_perm_file = Gtk.Entry()
        self.entry_perm_file.set_placeholder_text("Chọn file để xem/sửa quyền...")
        self.entry_perm_file.set_hexpand(True)
        row_file.pack_start(self.entry_perm_file, True, True, 0)

        btn_choose_perm = Gtk.Button(label="Chọn file")
        btn_choose_perm.connect("clicked", self._on_choose_perm_file)
        row_file.pack_start(btn_choose_perm, False, False, 0)

        # Thông tin hiện tại
        info_frame = Gtk.Frame(label="Thông tin hiện tại")
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_border_width(8)
        info_frame.add(info_box)
        vbox.pack_start(info_frame, False, False, 0)

        self.lbl_perm_info = Gtk.Label(label="Chưa chọn file")
        self.lbl_perm_info.set_halign(Gtk.Align.START)
        self.lbl_perm_info.set_line_wrap(True)
        info_box.pack_start(self.lbl_perm_info, False, False, 0)

        # Thay đổi quyền (chmod)
        chmod_frame = Gtk.Frame(label="Thay đổi quyền (chmod)")
        chmod_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        chmod_box.set_border_width(8)
        chmod_frame.add(chmod_box)
        vbox.pack_start(chmod_frame, False, False, 0)

        # Quyền octal
        row_octal = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chmod_box.pack_start(row_octal, False, False, 0)

        row_octal.pack_start(Gtk.Label(label="Quyền (octal):"), False, False, 0)
        self.entry_chmod = Gtk.Entry()
        self.entry_chmod.set_placeholder_text("VD: 0755")
        self.entry_chmod.set_width_chars(8)
        row_octal.pack_start(self.entry_chmod, False, False, 0)

        btn_chmod = Gtk.Button(label="Áp dụng chmod")
        btn_chmod.get_style_context().add_class("btn-primary")
        btn_chmod.connect("clicked", self._on_chmod)
        row_octal.pack_start(btn_chmod, False, False, 0)

        # Checkboxes quyền chi tiết
        perms_grid = Gtk.Grid()
        perms_grid.set_column_spacing(12)
        perms_grid.set_row_spacing(4)
        chmod_box.pack_start(perms_grid, False, False, 0)

        headers = ["", "Đọc (r)", "Ghi (w)", "Thực thi (x)"]
        for i, h in enumerate(headers):
            lbl = Gtk.Label(label=h)
            lbl.set_halign(Gtk.Align.START)
            if i == 0:
                lbl.get_style_context().add_class("metadata-label")
            perms_grid.attach(lbl, i, 0, 1, 1)

        self._perm_checks = {}
        for row_idx, (group_name, prefix) in enumerate([
            ("Owner", "u"), ("Group", "g"), ("Others", "o")
        ], start=1):
            lbl = Gtk.Label(label=group_name)
            lbl.set_halign(Gtk.Align.START)
            lbl.get_style_context().add_class("perm-label")
            perms_grid.attach(lbl, 0, row_idx, 1, 1)
            for col_idx, perm in enumerate(["r", "w", "x"], start=1):
                cb = Gtk.CheckButton()
                cb.connect("toggled", self._on_perm_check_toggled)
                perms_grid.attach(cb, col_idx, row_idx, 1, 1)
                self._perm_checks[f"{prefix}{perm}"] = cb

        # Thay đổi sở hữu (chown)
        chown_frame = Gtk.Frame(label="Thay đổi sở hữu (chown)")
        chown_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chown_box.set_border_width(8)
        chown_frame.add(chown_box)
        vbox.pack_start(chown_frame, False, False, 0)

        chown_box.pack_start(Gtk.Label(label="UID:"), False, False, 0)
        self.entry_uid = Gtk.Entry()
        self.entry_uid.set_width_chars(8)
        self.entry_uid.set_placeholder_text("1000")
        chown_box.pack_start(self.entry_uid, False, False, 0)

        chown_box.pack_start(Gtk.Label(label="GID:"), False, False, 4)
        self.entry_gid = Gtk.Entry()
        self.entry_gid.set_width_chars(8)
        self.entry_gid.set_placeholder_text("1000")
        chown_box.pack_start(self.entry_gid, False, False, 0)

        btn_chown = Gtk.Button(label="Áp dụng chown")
        btn_chown.get_style_context().add_class("btn-primary")
        btn_chown.connect("clicked", self._on_chown)
        chown_box.pack_start(btn_chown, False, False, 0)

        # Output log
        self.lbl_perm_output = Gtk.Label(label="")
        self.lbl_perm_output.set_halign(Gtk.Align.START)
        self.lbl_perm_output.get_style_context().add_class("metadata-label")
        vbox.pack_start(self.lbl_perm_output, False, False, 0)

        self.sub_notebook.append_page(vbox, Gtk.Label(label="Quyền"))

    # ═══════════════════════════════════════════════════════════
    # FILE OPERATIONS
    # ═══════════════════════════════════════════════════════════

    def _on_choose_file(self, button: Gtk.Button) -> None:
        """Mở FileChooser dialog, auto-read khi chọn."""
        dialog = Gtk.FileChooserDialog(
            title="Chọn file",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            self.entry_file.set_text(filepath)
            self._selected_file = filepath
            self._load_metadata(filepath)
            # Auto-read khi chọn file
            thread = threading.Thread(target=self._do_read_file, args=(filepath,), daemon=True)
            thread.start()
        dialog.destroy()

    def _on_entry_file_activate(self, entry: Gtk.Entry) -> None:
        """Khi nhấn Enter trên entry file, đọc file."""
        path = entry.get_text().strip()
        if path:
            self._selected_file = path
            self._load_metadata(path)
            thread = threading.Thread(target=self._do_read_file, args=(path,), daemon=True)
            thread.start()

    def _load_metadata(self, path: str) -> None:
        """Hiển thị metadata file bằng backend info."""
        thread = threading.Thread(target=self._do_load_metadata, args=(path,), daemon=True)
        thread.start()

    def _do_load_metadata(self, path: str) -> None:
        """Thread phụ: gọi file_mgr info."""
        try:
            result = subprocess.run(
                [self._backend, 'info', path],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout.strip()
            if output.startswith("INFO|"):
                parts = output.split("|")
                size = format_bytes(int(parts[1]))
                perms = format_permissions(int(parts[2], 8) | 0o100000)
                mtime = format_datetime(float(parts[3]))
                uid = parts[4] if len(parts) > 4 else "—"
                gid = parts[5] if len(parts) > 5 else "—"
                owner = parts[6] if len(parts) > 6 else "—"
                group = parts[7] if len(parts) > 7 else "—"
                GLib.idle_add(
                    self.lbl_metadata.set_text,
                    f"Size: {size}  |  Quyền: {perms}  |  Owner: {owner}  |  Sửa: {mtime}")
                # Cập nhật tab Quyền
                GLib.idle_add(self._update_perm_info, path, parts)
            elif output.startswith("ERROR|"):
                GLib.idle_add(self.lbl_metadata.set_text, f"Lỗi: {output.split('|', 1)[1]}")
        except Exception as e:
            GLib.idle_add(self.lbl_metadata.set_text, f"Lỗi: {e}")

    def _update_perm_info(self, path: str, info_parts: list) -> None:
        """Cập nhật thông tin trên tab Quyền."""
        if len(info_parts) >= 8:
            perms_octal = info_parts[2]
            uid = info_parts[4]
            gid = info_parts[5]
            owner = info_parts[6]
            group = info_parts[7]
            perms_str = format_permissions(int(perms_octal, 8) | 0o100000)

            self.lbl_perm_info.set_text(
                f"File: {path}\n"
                f"Quyền: {perms_str} ({perms_octal})\n"
                f"Owner: {owner} (UID: {uid})  |  Group: {group} (GID: {gid})"
            )

            self.entry_perm_file.set_text(path)
            self.entry_chmod.set_text(perms_octal)
            self.entry_uid.set_text(uid)
            self.entry_gid.set_text(gid)

            # Cập nhật checkboxes
            mode = int(perms_octal, 8)
            self._perm_checks["ur"].set_active(bool(mode & 0o400))
            self._perm_checks["uw"].set_active(bool(mode & 0o200))
            self._perm_checks["ux"].set_active(bool(mode & 0o100))
            self._perm_checks["gr"].set_active(bool(mode & 0o040))
            self._perm_checks["gw"].set_active(bool(mode & 0o020))
            self._perm_checks["gx"].set_active(bool(mode & 0o010))
            self._perm_checks["or"].set_active(bool(mode & 0o004))
            self._perm_checks["ow"].set_active(bool(mode & 0o002))
            self._perm_checks["ox"].set_active(bool(mode & 0o001))

    def _on_perm_check_toggled(self, check: Gtk.CheckButton) -> None:
        """Khi checkbox quyền thay đổi, cập nhật octal entry."""
        mode = 0
        if self._perm_checks["ur"].get_active(): mode |= 0o400
        if self._perm_checks["uw"].get_active(): mode |= 0o200
        if self._perm_checks["ux"].get_active(): mode |= 0o100
        if self._perm_checks["gr"].get_active(): mode |= 0o040
        if self._perm_checks["gw"].get_active(): mode |= 0o020
        if self._perm_checks["gx"].get_active(): mode |= 0o010
        if self._perm_checks["or"].get_active(): mode |= 0o004
        if self._perm_checks["ow"].get_active(): mode |= 0o002
        if self._perm_checks["ox"].get_active(): mode |= 0o001
        self.entry_chmod.set_text(f"{mode:04o}")

    # ─── Đọc file ────────────────────────────────────────────

    def _do_read_file(self, path: str) -> None:
        """Thread phụ: gọi file_mgr read, parse TEXT + HEX."""
        try:
            result = subprocess.run(
                [self._backend, 'read', path],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.startswith("ERROR|"):
                GLib.idle_add(self._show_error, result.stdout.split("|", 1)[1])
                return

            output = result.stdout
            text_content = ""
            hex_content = ""

            # Parse TEXT_START ... TEXT_END
            if "TEXT_START" in output and "TEXT_END" in output:
                start = output.index("TEXT_START") + len("TEXT_START\n")
                end = output.index("\nTEXT_END")
                text_content = output[start:end]

            # Parse HEX_START ... HEX_END
            if "HEX_START" in output and "HEX_END" in output:
                start = output.index("HEX_START") + len("HEX_START\n")
                end = output.index("\nHEX_END")
                hex_content = output[start:end]

            GLib.idle_add(self._update_file_views, text_content, hex_content)

        except subprocess.TimeoutExpired:
            GLib.idle_add(self._show_error, "Timeout khi đọc file")
        except FileNotFoundError:
            GLib.idle_add(self._show_error, "Không tìm thấy backend/file_mgr. Hãy chạy 'make'.")
        except Exception as e:
            GLib.idle_add(self._show_error, f"Lỗi: {e}")

    def _update_file_views(self, text: str, hex_dump: str) -> None:
        """Cập nhật text view và hex view."""
        self.text_view.get_buffer().set_text(text)
        self.hex_view.get_buffer().set_text(hex_dump)

    # ─── Ghi file ────────────────────────────────────────────

    def _on_write_file(self, button: Gtk.Button) -> None:
        """Ghi nội dung vào file (overwrite hoặc append)."""
        path = self.entry_file.get_text().strip()
        if not path:
            self._show_error("Vui lòng chọn file trước khi ghi.")
            return

        buf = self.write_view.get_buffer()
        start, end = buf.get_bounds()
        content = buf.get_text(start, end, True)

        if not content:
            self._show_error("Vui lòng nhập nội dung cần ghi.")
            return

        mode = "append" if self.combo_write_mode.get_active() == 1 else "write"

        thread = threading.Thread(
            target=self._do_write_file, args=(path, content, mode), daemon=True)
        thread.start()

    def _do_write_file(self, path: str, content: str, mode: str) -> None:
        """Thread phụ: gọi file_mgr write hoặc append."""
        try:
            result = subprocess.run(
                [self._backend, mode, path, content],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout.strip()
            if output.startswith("WRITTEN|"):
                nbytes = output.split("|")[1]
                mode_label = "ghi thêm" if mode == "append" else "ghi đè"
                GLib.idle_add(self._show_info, f"Đã {mode_label} {nbytes} bytes vào {path}")
                # Reload file
                self._do_read_file(path)
            elif output.startswith("ERROR|"):
                GLib.idle_add(self._show_error, output.split("|", 1)[1])
        except Exception as e:
            GLib.idle_add(self._show_error, f"Lỗi ghi file: {e}")

    # ─── inotify ─────────────────────────────────────────────

    def _on_choose_watch_file(self, button: Gtk.Button) -> None:
        """Chọn file để theo dõi."""
        dialog = Gtk.FileChooserDialog(
            title="Chọn file để theo dõi",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.entry_watch.set_text(dialog.get_filename())
        dialog.destroy()

    def _on_choose_watch_folder(self, button: Gtk.Button) -> None:
        """Chọn thư mục để theo dõi."""
        dialog = Gtk.FileChooserDialog(
            title="Chọn thư mục để theo dõi",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.entry_watch.set_text(dialog.get_filename())
        dialog.destroy()

    def _on_start_watch(self, button: Gtk.Button) -> None:
        """Bắt đầu inotify watch."""
        path = self.entry_watch.get_text().strip()
        if not path:
            self._show_error("Vui lòng chọn file hoặc thư mục cần theo dõi.")
            return

        # Dừng watch cũ nếu có
        self._stop_inotify()

        # Xóa log cũ
        self.inotify_view.get_buffer().set_text("")

        try:
            self._inotify_proc = subprocess.Popen(
                [self._backend, 'watch', path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line-buffered
            )

            # Thread đọc stdout
            self._inotify_thread = threading.Thread(
                target=self._read_inotify_output, daemon=True)
            self._inotify_thread.start()

            self._append_inotify_log(f"✅ Đang theo dõi: {path}")
            self.lbl_watch_status.set_text(f"Đang theo dõi: {os.path.basename(path)}")

        except FileNotFoundError:
            self._show_error("Không tìm thấy backend/file_mgr. Hãy chạy 'make'.")
        except Exception as e:
            self._show_error(f"Lỗi khởi động inotify: {e}")

    def _read_inotify_output(self) -> None:
        """Thread phụ: đọc stdout từ inotify process, update GUI."""
        try:
            proc = self._inotify_proc
            if proc and proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        GLib.idle_add(self._append_inotify_log, line)
        except Exception:
            pass

    def _append_inotify_log(self, text: str) -> None:
        """Thêm dòng vào inotify log (main thread)."""
        buf = self.inotify_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        mark = buf.get_insert()
        self.inotify_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _on_stop_watch(self, button: Gtk.Button) -> None:
        """Dừng inotify watch."""
        self._stop_inotify()
        self._append_inotify_log("⏹ Đã dừng theo dõi.")
        self.lbl_watch_status.set_text("Đã dừng")

    def _stop_inotify(self) -> None:
        """Dừng inotify subprocess."""
        if self._inotify_proc:
            try:
                self._inotify_proc.terminate()
                self._inotify_proc.wait(timeout=2)
            except Exception:
                try:
                    self._inotify_proc.kill()
                except Exception:
                    pass
            self._inotify_proc = None

    # ─── Permissions (chmod / chown) ─────────────────────────

    def _on_choose_perm_file(self, button: Gtk.Button) -> None:
        """Chọn file cho tab quyền."""
        dialog = Gtk.FileChooserDialog(
            title="Chọn file",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            self.entry_perm_file.set_text(filepath)
            self._load_metadata(filepath)
        dialog.destroy()

    def _on_chmod(self, button: Gtk.Button) -> None:
        """Thay đổi quyền file."""
        path = self.entry_perm_file.get_text().strip()
        mode = self.entry_chmod.get_text().strip()
        if not path or not mode:
            self._show_error("Vui lòng chọn file và nhập quyền.")
            return
        thread = threading.Thread(
            target=self._do_chmod, args=(path, mode), daemon=True)
        thread.start()

    def _do_chmod(self, path: str, mode: str) -> None:
        """Thread phụ: gọi file_mgr chmod."""
        try:
            result = subprocess.run(
                [self._backend, 'chmod', path, mode],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout.strip()
            if output.startswith("OK|"):
                GLib.idle_add(self.lbl_perm_output.set_text,
                              f"✅ Đã thay đổi quyền thành {mode}")
                # Reload metadata
                self._do_load_metadata(path)
            elif output.startswith("ERROR|"):
                GLib.idle_add(self.lbl_perm_output.set_text,
                              f"❌ {output.split('|', 1)[1]}")
        except Exception as e:
            GLib.idle_add(self.lbl_perm_output.set_text, f"❌ Lỗi: {e}")

    def _on_chown(self, button: Gtk.Button) -> None:
        """Thay đổi sở hữu file."""
        path = self.entry_perm_file.get_text().strip()
        uid = self.entry_uid.get_text().strip()
        gid = self.entry_gid.get_text().strip()
        if not path or not uid or not gid:
            self._show_error("Vui lòng chọn file, nhập UID và GID.")
            return
        thread = threading.Thread(
            target=self._do_chown, args=(path, uid, gid), daemon=True)
        thread.start()

    def _do_chown(self, path: str, uid: str, gid: str) -> None:
        """Thread phụ: gọi file_mgr chown."""
        try:
            result = subprocess.run(
                [self._backend, 'chown', path, uid, gid],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout.strip()
            if output.startswith("OK|"):
                GLib.idle_add(self.lbl_perm_output.set_text,
                              f"✅ Đã thay đổi sở hữu: UID={uid}, GID={gid}")
                self._do_load_metadata(path)
            elif output.startswith("ERROR|"):
                GLib.idle_add(self.lbl_perm_output.set_text,
                              f"❌ {output.split('|', 1)[1]}")
        except Exception as e:
            GLib.idle_add(self.lbl_perm_output.set_text, f"❌ Lỗi: {e}")

    # ─── mmap demo ───────────────────────────────────────────

    def _on_mmap_demo(self, button: Gtk.Button) -> None:
        """So sánh hiệu năng mmap vs read — hiển thị inline."""
        path = self.entry_file.get_text().strip()
        if not path:
            self._show_error("Vui lòng chọn file trước khi chạy mmap demo.")
            return
        self.lbl_mmap_result.set_text("⏳ Đang chạy...")
        self.lbl_mmap_result.show()
        thread = threading.Thread(target=self._do_mmap_demo, args=(path,), daemon=True)
        thread.start()

    def _do_mmap_demo(self, path: str) -> None:
        """Thread phụ: gọi file_mgr mmap."""
        try:
            result = subprocess.run(
                [self._backend, 'mmap', path],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if output.startswith("MMAP|"):
                parts = output.split("|")
                mmap_us = int(parts[1])
                read_us = int(parts[2])
                winner = "mmap nhanh hơn" if mmap_us < read_us else "read nhanh hơn"
                diff = abs(read_us - mmap_us)
                msg = (f"⚡ mmap: {mmap_us} μs  |  read: {read_us} μs  "
                       f"|  {winner} {diff} μs")
                GLib.idle_add(self.lbl_mmap_result.set_text, msg)
                GLib.idle_add(self.lbl_mmap_result.show)
            elif output.startswith("ERROR|"):
                GLib.idle_add(self.lbl_mmap_result.set_text,
                              f"❌ {output.split('|', 1)[1]}")
        except Exception as e:
            GLib.idle_add(self.lbl_mmap_result.set_text, f"❌ Lỗi mmap: {e}")

    # ─── Dialogs ─────────────────────────────────────────────

    def _show_error(self, msg: str) -> None:
        """Hiển thị dialog lỗi."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=msg
        )
        dialog.run()
        dialog.destroy()

    def _show_info(self, msg: str) -> None:
        """Hiển thị dialog thông tin."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=msg
        )
        dialog.run()
        dialog.destroy()

    # ─── Cleanup ─────────────────────────────────────────────

    def cleanup(self) -> None:
        """Cleanup khi đóng app."""
        self._stop_inotify()

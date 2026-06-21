"""
tab_network.py — Tab thông tin mạng + công cụ mạng.
Sub-tabs: Tổng quan (interfaces, traffic, routing) + Công cụ (DNS, Traceroute, ARP).
"""

import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from utils.helpers import get_backend_path, format_bytes


class TabNetwork(Gtk.Box):
    """
    Tab Network Info — chia thành 2 sub-tabs:
    - Tổng quan: Network Interfaces + Traffic Stats + Routing Table
    - Công cụ: Ping + DNS Lookup + Traceroute + ARP Table
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_border_width(12)

        self._backend = get_backend_path("network_info")
        self._ping_proc = None
        self._traceroute_proc = None

        self._build_ui()
        # Load dữ liệu ban đầu
        self._refresh_all()

    def _build_ui(self) -> None:
        """Xây dựng giao diện tab Network."""

        # === Nút Refresh ===
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_bottom(8)
        self.pack_start(toolbar, False, False, 0)

        btn_refresh = Gtk.Button(label="Làm mới tất cả")
        btn_refresh.get_style_context().add_class("btn-primary")
        btn_refresh.connect("clicked", lambda _: self._refresh_all())
        toolbar.pack_start(btn_refresh, False, False, 0)

        # === Sub-notebook ===
        self.sub_notebook = Gtk.Notebook()
        self.pack_start(self.sub_notebook, True, True, 0)

        # Sub-tab 1: Tổng quan
        self._build_overview_tab()
        # Sub-tab 2: Công cụ
        self._build_tools_tab()

    # ═══════════════════════════════════════════════════════════
    # SUB-TAB 1: Tổng quan
    # ═══════════════════════════════════════════════════════════

    def _build_overview_tab(self) -> None:
        """Sub-tab tổng quan mạng."""
        scroll_main = Gtk.ScrolledWindow()
        scroll_main.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_border_width(8)
        scroll_main.add(content)

        # === 1. Network Interfaces ===
        lbl_iface = Gtk.Label(label="Network Interfaces")
        lbl_iface.set_halign(Gtk.Align.START)
        lbl_iface.get_style_context().add_class("section-label")
        content.pack_start(lbl_iface, False, False, 0)

        scroll_iface = Gtk.ScrolledWindow()
        scroll_iface.set_size_request(-1, 130)
        scroll_iface.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        content.pack_start(scroll_iface, False, True, 0)

        # ListStore: Name, IPv4, IPv6, MAC, MTU, Status
        self.iface_store = Gtk.ListStore(str, str, str, str, str, str)
        self.iface_tree = Gtk.TreeView(model=self.iface_store)
        self.iface_tree.set_headers_visible(True)

        for title, col_id, width in [
            ("Tên", 0, 80), ("IPv4", 1, 130), ("IPv6", 2, 180),
            ("MAC", 3, 140), ("MTU", 4, 60), ("Trạng thái", 5, 60)
        ]:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            self.iface_tree.append_column(col)

        scroll_iface.add(self.iface_tree)

        # === 2. Traffic Stats ===
        lbl_traffic = Gtk.Label(label="Traffic Stats")
        lbl_traffic.set_halign(Gtk.Align.START)
        lbl_traffic.get_style_context().add_class("section-label")
        content.pack_start(lbl_traffic, False, False, 8)

        self.lbl_traffic_data = Gtk.Label(label="Đang tải...")
        self.lbl_traffic_data.set_halign(Gtk.Align.START)
        self.lbl_traffic_data.set_line_wrap(True)
        content.pack_start(self.lbl_traffic_data, False, False, 0)

        # === 3. Routing Table ===
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content.pack_start(sep2, False, False, 2)

        lbl_route = Gtk.Label(label="Routing Table")
        lbl_route.set_halign(Gtk.Align.START)
        lbl_route.get_style_context().add_class("section-label")
        content.pack_start(lbl_route, False, False, 0)

        scroll_route = Gtk.ScrolledWindow()
        scroll_route.set_size_request(-1, 100)
        scroll_route.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        content.pack_start(scroll_route, False, True, 0)

        # ListStore: Destination, Gateway, Netmask, Interface, Flags
        self.route_store = Gtk.ListStore(str, str, str, str, str)
        self.route_tree = Gtk.TreeView(model=self.route_store)
        self.route_tree.set_headers_visible(True)

        for title, col_id, width in [
            ("Destination", 0, 120), ("Gateway", 1, 120),
            ("Netmask", 2, 120), ("Interface", 3, 80), ("Flags", 4, 60)
        ]:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            self.route_tree.append_column(col)

        scroll_route.add(self.route_tree)

        self.sub_notebook.append_page(scroll_main, Gtk.Label(label="Tổng quan"))

    # ═══════════════════════════════════════════════════════════
    # SUB-TAB 2: Công cụ
    # ═══════════════════════════════════════════════════════════

    def _build_tools_tab(self) -> None:
        """Sub-tab công cụ mạng: Ping, DNS, Traceroute, ARP."""
        scroll_main = Gtk.ScrolledWindow()
        scroll_main.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_border_width(8)
        scroll_main.add(content)

        sg = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        # === 1. Ping ===
        lbl_ping = Gtk.Label(label="Ping Host")
        lbl_ping.set_halign(Gtk.Align.START)
        lbl_ping.get_style_context().add_class("section-label")
        content.pack_start(lbl_ping, False, False, 0)

        row_ping = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(row_ping, False, False, 0)

        lbl_ping_host = Gtk.Label(label="Host:")
        lbl_ping_host.set_xalign(0.0)
        sg.add_widget(lbl_ping_host)
        row_ping.pack_start(lbl_ping_host, False, False, 0)
        self.entry_ping = Gtk.Entry()
        self.entry_ping.set_text("8.8.8.8")
        self.entry_ping.set_hexpand(True)
        self.entry_ping.connect("activate", self._on_ping)
        row_ping.pack_start(self.entry_ping, True, True, 0)

        btn_ping = Gtk.Button(label="Ping")
        btn_ping.get_style_context().add_class("btn-success")
        btn_ping.connect("clicked", self._on_ping)
        row_ping.pack_start(btn_ping, False, False, 0)

        self.scroll_ping = Gtk.ScrolledWindow()
        self.scroll_ping.set_size_request(-1, 100)
        self.scroll_ping.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroll_ping.get_style_context().add_class("output-panel")
        self.scroll_ping.set_no_show_all(True)
        self.scroll_ping.hide()
        content.pack_start(self.scroll_ping, False, True, 0)

        self.ping_view = Gtk.TextView()
        self.ping_view.set_editable(False)
        self.ping_view.set_monospace(True)
        self.scroll_ping.add(self.ping_view)

        # === 2. DNS Lookup ===
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content.pack_start(sep1, False, False, 2)

        lbl_dns = Gtk.Label(label="DNS Lookup")
        lbl_dns.set_halign(Gtk.Align.START)
        lbl_dns.get_style_context().add_class("section-label")
        content.pack_start(lbl_dns, False, False, 0)

        row_dns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(row_dns, False, False, 0)

        lbl_dns_host = Gtk.Label(label="Hostname:")
        lbl_dns_host.set_xalign(0.0)
        sg.add_widget(lbl_dns_host)
        row_dns.pack_start(lbl_dns_host, False, False, 0)
        self.entry_dns = Gtk.Entry()
        self.entry_dns.set_text("google.com")
        self.entry_dns.set_hexpand(True)
        self.entry_dns.connect("activate", self._on_dns_lookup)
        row_dns.pack_start(self.entry_dns, True, True, 0)

        btn_dns = Gtk.Button(label="Phân giải")
        btn_dns.get_style_context().add_class("btn-primary")
        btn_dns.connect("clicked", self._on_dns_lookup)
        row_dns.pack_start(btn_dns, False, False, 0)

        self.scroll_dns = Gtk.ScrolledWindow()
        self.scroll_dns.set_size_request(-1, 80)
        self.scroll_dns.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroll_dns.get_style_context().add_class("output-panel")
        self.scroll_dns.set_no_show_all(True)
        self.scroll_dns.hide()
        content.pack_start(self.scroll_dns, False, True, 0)

        self.dns_view = Gtk.TextView()
        self.dns_view.set_editable(False)
        self.dns_view.set_monospace(True)
        self.scroll_dns.add(self.dns_view)

        # === 3. Traceroute ===
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content.pack_start(sep2, False, False, 2)

        lbl_trace = Gtk.Label(label="Traceroute")
        lbl_trace.set_halign(Gtk.Align.START)
        lbl_trace.get_style_context().add_class("section-label")
        content.pack_start(lbl_trace, False, False, 0)

        row_trace = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(row_trace, False, False, 0)

        lbl_trace_host = Gtk.Label(label="Host:")
        lbl_trace_host.set_xalign(0.0)
        sg.add_widget(lbl_trace_host)
        row_trace.pack_start(lbl_trace_host, False, False, 0)
        self.entry_trace = Gtk.Entry()
        self.entry_trace.set_text("8.8.8.8")
        self.entry_trace.set_hexpand(True)
        self.entry_trace.connect("activate", self._on_traceroute)
        row_trace.pack_start(self.entry_trace, True, True, 0)

        btn_trace = Gtk.Button(label="Traceroute")
        btn_trace.get_style_context().add_class("btn-primary")
        btn_trace.connect("clicked", self._on_traceroute)
        row_trace.pack_start(btn_trace, False, False, 0)

        btn_stop_trace = Gtk.Button(label="Dừng")
        btn_stop_trace.get_style_context().add_class("btn-danger")
        btn_stop_trace.connect("clicked", self._on_stop_traceroute)
        row_trace.pack_start(btn_stop_trace, False, False, 0)

        self.scroll_trace = Gtk.ScrolledWindow()
        self.scroll_trace.set_size_request(-1, 120)
        self.scroll_trace.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroll_trace.get_style_context().add_class("output-panel")
        self.scroll_trace.set_no_show_all(True)
        self.scroll_trace.hide()
        content.pack_start(self.scroll_trace, False, True, 0)

        self.trace_view = Gtk.TextView()
        self.trace_view.set_editable(False)
        self.trace_view.set_monospace(True)
        self.scroll_trace.add(self.trace_view)

        # === 4. ARP Table ===
        sep3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content.pack_start(sep3, False, False, 2)

        lbl_arp = Gtk.Label(label="ARP Table")
        lbl_arp.set_halign(Gtk.Align.START)
        lbl_arp.get_style_context().add_class("section-label")
        content.pack_start(lbl_arp, False, False, 0)

        row_arp = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(row_arp, False, False, 0)

        btn_arp = Gtk.Button(label="Tải ARP Table")
        btn_arp.connect("clicked", self._on_refresh_arp)
        row_arp.pack_start(btn_arp, False, False, 0)

        scroll_arp = Gtk.ScrolledWindow()
        scroll_arp.set_size_request(-1, 100)
        scroll_arp.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        content.pack_start(scroll_arp, False, True, 0)

        # ListStore: IP, HW Type, Flags, MAC, Mask, Device
        self.arp_store = Gtk.ListStore(str, str, str, str, str, str)
        self.arp_tree = Gtk.TreeView(model=self.arp_store)
        self.arp_tree.set_headers_visible(True)

        for title, col_id, width in [
            ("IP Address", 0, 130), ("HW Type", 1, 70), ("Flags", 2, 50),
            ("MAC", 3, 150), ("Mask", 4, 50), ("Device", 5, 80)
        ]:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            self.arp_tree.append_column(col)

        scroll_arp.add(self.arp_tree)

        self.sub_notebook.append_page(scroll_main, Gtk.Label(label="Công cụ"))

    # ─── Refresh tất cả ──────────────────────────────────────

    def _refresh_all(self) -> None:
        """Refresh tất cả thông tin mạng trong thread phụ."""
        thread = threading.Thread(target=self._do_refresh_all, daemon=True)
        thread.start()

    def _do_refresh_all(self) -> None:
        """Thread phụ: gọi backend cho interfaces, traffic, route."""
        self._do_refresh_interfaces()
        self._do_refresh_traffic()
        self._do_refresh_route()

    def _do_refresh_interfaces(self) -> None:
        """Gọi network_info interfaces."""
        try:
            result = subprocess.run(
                [self._backend, 'interfaces'],
                capture_output=True, text=True, timeout=5
            )
            entries = []
            for line in result.stdout.strip().split('\n'):
                if not line or line.startswith("ERROR"):
                    continue
                parts = line.split('|')
                if len(parts) >= 6:
                    entries.append((parts[0], parts[1], parts[2],
                                    parts[3], parts[4], parts[5]))
            GLib.idle_add(self._update_iface_store, entries)
        except FileNotFoundError:
            GLib.idle_add(self._show_error_label,
                          "Không tìm thấy backend/network_info. Hãy chạy 'make'.")
        except Exception as e:
            GLib.idle_add(self._show_error_label, f"Lỗi interfaces: {e}")

    def _update_iface_store(self, entries: list) -> None:
        """Cập nhật bảng interfaces."""
        self.iface_store.clear()
        for row in entries:
            self.iface_store.append(list(row))

    def _do_refresh_traffic(self) -> None:
        """Gọi network_info traffic."""
        try:
            result = subprocess.run(
                [self._backend, 'traffic'],
                capture_output=True, text=True, timeout=5
            )
            lines = []
            for line in result.stdout.strip().split('\n'):
                if not line or line.startswith("ERROR"):
                    continue
                parts = line.split('|')
                if len(parts) >= 3:
                    iface = parts[0]
                    rx = format_bytes(int(parts[1]))
                    tx = format_bytes(int(parts[2]))
                    lines.append(f"  {iface} — Nhận: {rx}  |  Gửi: {tx}")
            text = "\n".join(lines) if lines else "Không có dữ liệu"
            GLib.idle_add(self.lbl_traffic_data.set_text, text)
        except Exception as e:
            GLib.idle_add(self.lbl_traffic_data.set_text, f"Lỗi: {e}")

    def _do_refresh_route(self) -> None:
        """Gọi network_info route."""
        try:
            result = subprocess.run(
                [self._backend, 'route'],
                capture_output=True, text=True, timeout=5
            )
            entries = []
            for line in result.stdout.strip().split('\n'):
                if not line or line.startswith("ERROR"):
                    continue
                parts = line.split('|')
                if len(parts) >= 5:
                    entries.append((parts[0], parts[1], parts[2],
                                    parts[3], parts[4]))
            GLib.idle_add(self._update_route_store, entries)
        except Exception as e:
            GLib.idle_add(self._show_error_label, f"Lỗi route: {e}")

    def _update_route_store(self, entries: list) -> None:
        """Cập nhật bảng routing."""
        self.route_store.clear()
        for row in entries:
            self.route_store.append(list(row))

    # ─── Ping ────────────────────────────────────────────────

    def _on_ping(self, widget) -> None:
        """Chạy ping (4 gói) tới host nhập."""
        host = self.entry_ping.get_text().strip()
        if not host:
            return

        # Dừng ping cũ
        self._stop_ping()

        # Hiện output panel và xóa output cũ
        self.scroll_ping.show_all()
        self.ping_view.get_buffer().set_text("")

        thread = threading.Thread(target=self._do_ping, args=(host,), daemon=True)
        thread.start()

    def _do_ping(self, host: str) -> None:
        """Thread phụ: chạy ping -c 4, đọc output real-time."""
        try:
            self._ping_proc = subprocess.Popen(
                ['ping', '-c', '4', host],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in self._ping_proc.stdout:
                GLib.idle_add(self._append_ping, line.rstrip())

            self._ping_proc.wait()
            self._ping_proc = None

        except FileNotFoundError:
            GLib.idle_add(self._append_ping, "Lệnh 'ping' không tìm thấy.")
        except Exception as e:
            GLib.idle_add(self._append_ping, f"Lỗi ping: {e}")

    def _append_ping(self, text: str) -> None:
        """Thêm dòng vào ping output."""
        buf = self.ping_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        mark = buf.get_insert()
        self.ping_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _stop_ping(self) -> None:
        """Dừng ping process."""
        if self._ping_proc:
            try:
                self._ping_proc.terminate()
                self._ping_proc.wait(timeout=2)
            except Exception:
                try:
                    self._ping_proc.kill()
                except Exception:
                    pass
            self._ping_proc = None

    # ─── DNS Lookup ──────────────────────────────────────────

    def _on_dns_lookup(self, widget) -> None:
        """Phân giải hostname."""
        hostname = self.entry_dns.get_text().strip()
        if not hostname:
            return

        self.scroll_dns.show_all()
        self.dns_view.get_buffer().set_text("Đang phân giải...\n")
        thread = threading.Thread(target=self._do_dns_lookup, args=(hostname,), daemon=True)
        thread.start()

    def _do_dns_lookup(self, hostname: str) -> None:
        """Thread phụ: gọi network_info dns."""
        try:
            result = subprocess.run(
                [self._backend, 'dns', hostname],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            lines = []
            for line in output.split('\n'):
                if line.startswith("DNS|"):
                    parts = line.split("|")
                    if len(parts) >= 4:
                        lines.append(f"  {parts[2]:6s}  →  {parts[3]}")
                elif line.startswith("ERROR|"):
                    lines.append(f"❌ {line.split('|', 1)[1]}")

            text = f"DNS Lookup: {hostname}\n" + "\n".join(lines) if lines else "Không có kết quả"
            GLib.idle_add(self._set_dns_text, text)
        except FileNotFoundError:
            GLib.idle_add(self._set_dns_text, "❌ Không tìm thấy backend/network_info.")
        except Exception as e:
            GLib.idle_add(self._set_dns_text, f"❌ Lỗi: {e}")

    def _set_dns_text(self, text: str) -> None:
        """Cập nhật DNS view."""
        self.dns_view.get_buffer().set_text(text)

    # ─── Traceroute ──────────────────────────────────────────

    def _on_traceroute(self, widget) -> None:
        """Chạy traceroute tới host."""
        host = self.entry_trace.get_text().strip()
        if not host:
            return

        self._stop_traceroute()
        self.scroll_trace.show_all()
        self.trace_view.get_buffer().set_text("")

        thread = threading.Thread(target=self._do_traceroute, args=(host,), daemon=True)
        thread.start()

    def _do_traceroute(self, host: str) -> None:
        """Thread phụ: chạy traceroute, stream output."""
        try:
            self._traceroute_proc = subprocess.Popen(
                ['traceroute', '-m', '15', host],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in self._traceroute_proc.stdout:
                GLib.idle_add(self._append_trace, line.rstrip())

            self._traceroute_proc.wait()
            self._traceroute_proc = None

        except FileNotFoundError:
            GLib.idle_add(self._append_trace,
                          "Lệnh 'traceroute' không tìm thấy. Cài: sudo apt install traceroute")
        except Exception as e:
            GLib.idle_add(self._append_trace, f"Lỗi traceroute: {e}")

    def _append_trace(self, text: str) -> None:
        """Thêm dòng vào traceroute output."""
        buf = self.trace_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        mark = buf.get_insert()
        self.trace_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _on_stop_traceroute(self, button) -> None:
        """Dừng traceroute."""
        self._stop_traceroute()

    def _stop_traceroute(self) -> None:
        """Dừng traceroute process."""
        if self._traceroute_proc:
            try:
                self._traceroute_proc.terminate()
                self._traceroute_proc.wait(timeout=2)
            except Exception:
                try:
                    self._traceroute_proc.kill()
                except Exception:
                    pass
            self._traceroute_proc = None

    # ─── ARP Table ───────────────────────────────────────────

    def _on_refresh_arp(self, button) -> None:
        """Refresh ARP table."""
        thread = threading.Thread(target=self._do_refresh_arp, daemon=True)
        thread.start()

    def _do_refresh_arp(self) -> None:
        """Thread phụ: gọi network_info arp."""
        try:
            result = subprocess.run(
                [self._backend, 'arp'],
                capture_output=True, text=True, timeout=5
            )
            entries = []
            for line in result.stdout.strip().split('\n'):
                if not line or line.startswith("ERROR"):
                    continue
                parts = line.split('|')
                if len(parts) >= 6:
                    entries.append((parts[0], parts[1], parts[2],
                                    parts[3], parts[4], parts[5]))
            GLib.idle_add(self._update_arp_store, entries)
        except FileNotFoundError:
            GLib.idle_add(self._show_error_label, "Không tìm thấy backend/network_info.")
        except Exception as e:
            GLib.idle_add(self._show_error_label, f"Lỗi ARP: {e}")

    def _update_arp_store(self, entries: list) -> None:
        """Cập nhật bảng ARP."""
        self.arp_store.clear()
        for row in entries:
            self.arp_store.append(list(row))

    # ─── Helpers ─────────────────────────────────────────────

    def _show_error_label(self, msg: str) -> None:
        """Hiển thị lỗi trong traffic label."""
        self.lbl_traffic_data.set_text(f"Lỗi: {msg}")

    # ─── Cleanup ─────────────────────────────────────────────

    def cleanup(self) -> None:
        """Cleanup khi đóng app."""
        self._stop_ping()
        self._stop_traceroute()

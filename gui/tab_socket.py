"""
tab_socket.py — Tab TCP/UDP Socket Chat (Server + Client trong cùng 1 cửa sổ) & Active Connections.
"""

import subprocess
import threading
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from utils.helpers import get_backend_path, format_time


class SocketCreateDialog(Gtk.Dialog):
    """Dialog tạo mới Socket Session (chỉ chọn Tên và Giao thức)."""
    def __init__(self, parent, default_name="Session 1"):
        super().__init__(title="Tạo Session Mới", transient_for=parent, flags=0)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        self.set_default_size(300, 150)
        self.set_border_width(10)

        box = self.get_content_area()
        box.set_spacing(8)

        # Name
        box.pack_start(Gtk.Label(label="Tên Session:", xalign=0), False, False, 0)
        self.entry_name = Gtk.Entry(text=default_name)
        box.pack_start(self.entry_name, False, False, 0)

        # Protocol
        box.pack_start(Gtk.Label(label="Giao thức:", xalign=0), False, False, 0)
        hbox_proto = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.radio_tcp = Gtk.RadioButton.new_with_label(None, "TCP")
        self.radio_udp = Gtk.RadioButton.new_with_label_from_widget(self.radio_tcp, "UDP")
        hbox_proto.pack_start(self.radio_tcp, False, False, 0)
        hbox_proto.pack_start(self.radio_udp, False, False, 0)
        box.pack_start(hbox_proto, False, False, 0)

        self.show_all()

    def get_data(self):
        return {
            "name": self.entry_name.get_text().strip(),
            "proto": "TCP" if self.radio_tcp.get_active() else "UDP"
        }


class SocketSession(Gtk.Box):
    """
    Một phiên bản độc lập của Socket Chat (Server + Client).
    Hỗ trợ TCP hoặc UDP.
    """

    def __init__(self, session_id, name, proto, manager_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_border_width(12)

        self.session_id = session_id
        self.session_name = name
        self.proto = proto
        self.manager_cb = manager_cb

        self._server_proc = None
        self._client_proc = None
        self._server_thread = None
        self._client_thread = None
        self._server_connected = False
        self._client_connected = False
        
        self.server_status_text = "Chưa khởi động"
        self.client_status_text = "Chưa kết nối"

        self._build_ui()

    def _build_ui(self) -> None:
        """Xây dựng giao diện tab Socket."""

        # Giao thức hiển thị
        lbl_proto = Gtk.Label(label=f"Giao thức: {self.proto}")
        lbl_proto.get_style_context().add_class("section-label")
        lbl_proto.set_halign(Gtk.Align.START)
        lbl_proto.set_margin_bottom(8)
        self.pack_start(lbl_proto, False, False, 0)

        # === Server + Client panels (cạnh nhau, homogeneous) ===
        panels = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        panels.set_homogeneous(True)
        self.pack_start(panels, False, False, 0)

        # --- Server panel ---
        server_frame = Gtk.Frame(label="SERVER")
        server_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        server_box.set_border_width(10)
        server_frame.add(server_box)
        panels.pack_start(server_frame, True, True, 0)

        sg_server = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        row_bind = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        server_box.pack_start(row_bind, False, False, 0)
        lbl_bind = Gtk.Label(label="Bind IP:")
        lbl_bind.set_xalign(0.0)
        sg_server.add_widget(lbl_bind)
        row_bind.pack_start(lbl_bind, False, False, 0)
        self.entry_server_bind = Gtk.Entry()
        self.entry_server_bind.set_text("0.0.0.0")
        self.entry_server_bind.set_hexpand(True)
        row_bind.pack_start(self.entry_server_bind, True, True, 0)

        row_port = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        server_box.pack_start(row_port, False, False, 0)
        lbl_port1 = Gtk.Label(label="Port:")
        lbl_port1.set_xalign(0.0)
        sg_server.add_widget(lbl_port1)
        row_port.pack_start(lbl_port1, False, False, 0)
        self.entry_server_port = Gtk.Entry()
        self.entry_server_port.set_text("9999")
        self.entry_server_port.set_hexpand(True)
        row_port.pack_start(self.entry_server_port, True, True, 0)

        self.lbl_server_status = Gtk.Label(label="Chưa khởi động")
        self.lbl_server_status.get_style_context().add_class("status-disconnected")
        server_box.pack_end(self.lbl_server_status, False, False, 0)

        self.btn_start_server = Gtk.Button(label="Khởi động Server")
        self.btn_start_server.get_style_context().add_class("btn-success")
        self.btn_start_server.set_hexpand(True)
        self.btn_start_server.connect("clicked", self._on_start_server)
        server_box.pack_end(self.btn_start_server, False, False, 0)

        # --- Client panel ---
        client_frame = Gtk.Frame(label="CLIENT")
        client_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        client_box.set_border_width(10)
        client_frame.add(client_box)
        panels.pack_start(client_frame, True, True, 0)

        sg_client = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        row_host = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        client_box.pack_start(row_host, False, False, 0)
        lbl_host = Gtk.Label(label="Host:")
        lbl_host.set_xalign(0.0)
        sg_client.add_widget(lbl_host)
        row_host.pack_start(lbl_host, False, False, 0)
        self.entry_client_host = Gtk.Entry()
        self.entry_client_host.set_text("127.0.0.1")
        self.entry_client_host.set_hexpand(True)
        row_host.pack_start(self.entry_client_host, True, True, 0)

        row_cport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        client_box.pack_start(row_cport, False, False, 0)
        lbl_port2 = Gtk.Label(label="Port:")
        lbl_port2.set_xalign(0.0)
        sg_client.add_widget(lbl_port2)
        row_cport.pack_start(lbl_port2, False, False, 0)
        self.entry_client_port = Gtk.Entry()
        self.entry_client_port.set_text("9999")
        self.entry_client_port.set_hexpand(True)
        row_cport.pack_start(self.entry_client_port, True, True, 0)

        self.lbl_client_status = Gtk.Label(label="Chưa kết nối")
        self.lbl_client_status.get_style_context().add_class("status-disconnected")
        client_box.pack_end(self.lbl_client_status, False, False, 0)

        self.btn_connect = Gtk.Button(label="Kết nối")
        self.btn_connect.get_style_context().add_class("btn-primary")
        self.btn_connect.set_hexpand(True)
        self.btn_connect.connect("clicked", self._on_connect_client)
        client_box.pack_end(self.btn_connect, False, False, 0)

        # === Separator ===
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(sep, False, False, 4)

        # === Chat log — 2 ô riêng cho Server và Client ===
        chat_label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        chat_label_box.set_homogeneous(True)
        self.pack_start(chat_label_box, False, False, 0)

        lbl_server_log = Gtk.Label(label="Server Log")
        lbl_server_log.get_style_context().add_class("section-label")
        chat_label_box.pack_start(lbl_server_log, True, True, 0)

        lbl_client_log = Gtk.Label(label="Client Log")
        lbl_client_log.get_style_context().add_class("section-label")
        chat_label_box.pack_start(lbl_client_log, True, True, 0)

        chat_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        chat_paned.set_position(450)
        self.pack_start(chat_paned, True, True, 0)

        # Server log
        scroll_server_log = Gtk.ScrolledWindow()
        scroll_server_log.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_server_log.get_style_context().add_class("chat-log")
        self.server_log_view = Gtk.TextView()
        self.server_log_view.set_editable(False)
        self.server_log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll_server_log.add(self.server_log_view)
        chat_paned.pack1(scroll_server_log, True, True)

        # Client log
        scroll_client_log = Gtk.ScrolledWindow()
        scroll_client_log.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_client_log.get_style_context().add_class("chat-log")
        self.client_log_view = Gtk.TextView()
        self.client_log_view.set_editable(False)
        self.client_log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll_client_log.add(self.client_log_view)
        chat_paned.pack2(scroll_client_log, True, True)

        # === Gửi message + Ngắt kết nối ===
        row_send = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row_send.set_margin_top(4)
        self.pack_start(row_send, False, False, 0)

        # Radio: gửi từ Server hay Client
        row_send.pack_start(Gtk.Label(label="Gửi từ:"), False, False, 0)
        self.radio_server = Gtk.RadioButton.new_with_label(None, "Server")
        self.radio_client = Gtk.RadioButton.new_with_label_from_widget(self.radio_server, "Client")
        self.radio_client.set_active(True)
        row_send.pack_start(self.radio_server, False, False, 0)
        row_send.pack_start(self.radio_client, False, False, 0)

        self.entry_msg = Gtk.Entry()
        self.entry_msg.set_placeholder_text("Nhập tin nhắn...")
        self.entry_msg.set_hexpand(True)
        self.entry_msg.connect("activate", self._on_send_message)
        row_send.pack_start(self.entry_msg, True, True, 0)

        btn_send = Gtk.Button(label="Gửi")
        btn_send.get_style_context().add_class("btn-primary")
        btn_send.connect("clicked", self._on_send_message)
        row_send.pack_start(btn_send, False, False, 0)

        btn_disconnect = Gtk.Button(label="Ngắt kết nối")
        btn_disconnect.get_style_context().add_class("btn-danger")
        btn_disconnect.connect("clicked", self._on_disconnect)
        row_send.pack_start(btn_disconnect, False, False, 0)

    # ─── Server ──────────────────────────────────────────────

    def _on_start_server(self, button: Gtk.Button) -> None:
        """Khởi động server."""
        if self._server_proc:
            self._append_server_log("⚠ Server đang chạy rồi.")
            return

        port = self.entry_server_port.get_text().strip()
        if not port:
            self._append_server_log("⚠ Vui lòng nhập port.")
            return

        bin_name = "socket_server" if self.proto == "TCP" else "socket_udp_server"
        backend = get_backend_path(bin_name)
        
        try:
            self._server_proc = subprocess.Popen(
                [backend, port],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self._server_thread = threading.Thread(
                target=self._read_server_output, daemon=True)
            self._server_thread.start()

            self._update_server_status("waiting", "Đang chờ...")

        except FileNotFoundError:
            self._append_server_log(f"❌ Không tìm thấy backend/{bin_name}. Hãy chạy 'make'.")
        except Exception as e:
            self._append_server_log(f"❌ Lỗi khởi động server: {e}")

    def _read_server_output(self) -> None:
        """Thread phụ: đọc stdout từ server process."""
        try:
            proc = self._server_proc
            if not proc or not proc.stdout:
                return
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("STATUS|"):
                    parts = line.split("|")
                    status = parts[1]
                    if status == "LISTENING":
                        msg = "Đang chờ kết nối..." if self.proto == "TCP" else "Đang chờ dữ liệu..."
                        log_msg = "🔄 Server đang chờ kết nối..." if self.proto == "TCP" else "🔄 Server đang chờ dữ liệu..."
                        GLib.idle_add(self._update_server_status, "waiting", msg)
                        GLib.idle_add(self._append_server_log, log_msg)
                    elif status == "CONNECTED":
                        client_ip = parts[2] if len(parts) > 2 else "unknown"
                        self._server_connected = True
                        msg = "Đã kết nối" if self.proto == "TCP" else f"Đang nhận từ {client_ip}"
                        log_msg = f"✅ Client đã kết nối từ {client_ip}" if self.proto == "TCP" else f"✅ Nhận dữ liệu từ {client_ip}"
                        GLib.idle_add(self._update_server_status, "connected", msg)
                        GLib.idle_add(self._append_server_log, log_msg)
                    elif status == "DISCONNECTED":
                        self._server_connected = False
                        GLib.idle_add(self._update_server_status, "disconnected", "Ngắt kết nối")
                        GLib.idle_add(self._append_server_log, "❌ Client đã ngắt kết nối.")
                elif line.startswith("RECV|"):
                    msg = line.split("|", 1)[1]
                    ts = format_time()
                    GLib.idle_add(self._append_server_log, f"[{ts}] ← [CLIENT]: {msg}")
                elif line.startswith("ERROR|"):
                    GLib.idle_add(self._append_server_log, f"❌ {line.split('|', 1)[1]}")
        except Exception:
            pass

    # ─── Client ──────────────────────────────────────────────

    def _on_connect_client(self, button: Gtk.Button) -> None:
        """Kết nối client tới server."""
        if self._client_proc:
            self._append_client_log("⚠ Client đang kết nối rồi.")
            return

        host = self.entry_client_host.get_text().strip()
        port = self.entry_client_port.get_text().strip()
        if not host or not port:
            self._append_client_log("⚠ Vui lòng nhập host và port.")
            return

        bin_name = "socket_client" if self.proto == "TCP" else "socket_udp_client"
        backend = get_backend_path(bin_name)
        
        try:
            self._client_proc = subprocess.Popen(
                [backend, host, port],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self._client_thread = threading.Thread(
                target=self._read_client_output, daemon=True)
            self._client_thread.start()

            self._update_client_status("waiting", "Đang kết nối...")

        except FileNotFoundError:
            self._append_client_log(f"❌ Không tìm thấy backend/{bin_name}. Hãy chạy 'make'.")
        except Exception as e:
            self._append_client_log(f"❌ Lỗi kết nối client: {e}")

    def _read_client_output(self) -> None:
        """Thread phụ: đọc stdout từ client process."""
        try:
            proc = self._client_proc
            if not proc or not proc.stdout:
                return
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("STATUS|"):
                    status = line.split("|")[1]
                    if status == "CONNECTED":
                        self._client_connected = True
                        msg = "Đã kết nối" if self.proto == "TCP" else "Đã sẵn sàng"
                        log_msg = "✅ Đã kết nối tới server." if self.proto == "TCP" else "✅ Đã sẵn sàng gửi/nhận UDP."
                        GLib.idle_add(self._update_client_status, "connected", msg)
                        GLib.idle_add(self._append_client_log, log_msg)
                    elif status == "DISCONNECTED":
                        self._client_connected = False
                        GLib.idle_add(self._update_client_status, "disconnected", "Ngắt kết nối")
                        GLib.idle_add(self._append_client_log, "❌ Đã mất kết nối với server.")
                elif line.startswith("RECV|"):
                    msg = line.split("|", 1)[1]
                    ts = format_time()
                    GLib.idle_add(self._append_client_log, f"[{ts}] ← [SERVER]: {msg}")
                elif line.startswith("ERROR|"):
                    GLib.idle_add(self._append_client_log, f"❌ {line.split('|', 1)[1]}")
                    GLib.idle_add(self._update_client_status, "disconnected", "Ngắt kết nối")
        except Exception:
            pass

    # ─── Gửi message ─────────────────────────────────────────

    def _on_send_message(self, widget) -> None:
        """Gửi message qua stdin của server hoặc client process."""
        msg = self.entry_msg.get_text().strip()
        if not msg:
            return

        ts = format_time()

        if self.radio_server.get_active():
            # Gửi từ server
            if not self._server_proc or (self.proto == "TCP" and not self._server_connected):
                self._append_server_log("⚠ Server chưa sẵn sàng hoặc chưa kết nối.")
                return
            try:
                self._server_proc.stdin.write(msg + "\n")
                self._server_proc.stdin.flush()
                self._append_server_log(f"[{ts}] → [GỬI]: {msg}")
            except Exception as e:
                self._append_server_log(f"❌ Lỗi gửi từ server: {e}")
        else:
            # Gửi từ client
            if not self._client_proc or (self.proto == "TCP" and not self._client_connected):
                self._append_client_log("⚠ Client chưa sẵn sàng hoặc chưa kết nối.")
                return
            try:
                self._client_proc.stdin.write(msg + "\n")
                self._client_proc.stdin.flush()
                self._append_client_log(f"[{ts}] → [GỬI]: {msg}")
            except Exception as e:
                self._append_client_log(f"❌ Lỗi gửi từ client: {e}")

        self.entry_msg.set_text("")

    # ─── Ngắt kết nối ────────────────────────────────────────

    def _on_disconnect(self, button: Gtk.Button) -> None:
        """Ngắt tất cả kết nối."""
        self._stop_server()
        self._stop_client()
        self._append_server_log("⛔ Đã ngắt kết nối.")
        self._append_client_log("⛔ Đã ngắt kết nối.")

    def _stop_server(self) -> None:
        """Dừng server process."""
        if self._server_proc:
            try:
                self._server_proc.terminate()
                self._server_proc.wait(timeout=2)
            except Exception:
                try:
                    self._server_proc.kill()
                except Exception:
                    pass
            self._server_proc = None
            self._server_connected = False
            self._update_server_status("disconnected", "Chưa khởi động")

    def _stop_client(self) -> None:
        """Dừng client process."""
        if self._client_proc:
            try:
                self._client_proc.terminate()
                self._client_proc.wait(timeout=2)
            except Exception:
                try:
                    self._client_proc.kill()
                except Exception:
                    pass
            self._client_proc = None
            self._client_connected = False
            self._update_client_status("disconnected", "Chưa kết nối")

    # ─── UI helpers ──────────────────────────────────────────

    def _append_server_log(self, text: str) -> None:
        buf = self.server_log_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        mark = buf.get_insert()
        self.server_log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _append_client_log(self, text: str) -> None:
        buf = self.client_log_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        mark = buf.get_insert()
        self.client_log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _update_server_status(self, status: str, text: str) -> None:
        ctx = self.lbl_server_status.get_style_context()
        ctx.remove_class("status-connected")
        ctx.remove_class("status-disconnected")
        ctx.remove_class("status-waiting")

        if status == "connected":
            ctx.add_class("status-connected")
        elif status == "waiting":
            ctx.add_class("status-waiting")
        else:
            ctx.add_class("status-disconnected")
            
        self.lbl_server_status.set_text(text)
        self.server_status_text = text
        if self.manager_cb:
            self.manager_cb()

    def _update_client_status(self, status: str, text: str) -> None:
        ctx = self.lbl_client_status.get_style_context()
        ctx.remove_class("status-connected")
        ctx.remove_class("status-disconnected")
        ctx.remove_class("status-waiting")

        if status == "connected":
            ctx.add_class("status-connected")
        elif status == "waiting":
            ctx.add_class("status-waiting")
        else:
            ctx.add_class("status-disconnected")
            
        self.lbl_client_status.set_text(text)
        self.client_status_text = text
        if self.manager_cb:
            self.manager_cb()

    def cleanup(self) -> None:
        self._stop_server()
        self._stop_client()


class TabSocket(Gtk.Box):
    """
    Tab quản lý Socket sử dụng Notebook chính.
    Sub-tab 1: Connections (Active Connections & Quản lý các phiên dạng ô lưới)
    Sub-tab 2: Sessions (Notebook chứa các tab chat thực tế)
    """
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.main_notebook = Gtk.Notebook()
        self.pack_start(self.main_notebook, True, True, 0)
        
        self._backend = get_backend_path("network_info")
        self.sessions = {} # id -> SocketSession
        self.session_counter = 0
        self.known_conns = {} # (proto, lip, lport, rip, rport) -> start_time
        
        self._build_connections_tab()
        self._build_sessions_tab()
        
        # Tạo 1 Session TCP mặc định
        self._create_session(1, {"name": "Session 1", "proto": "TCP"})
        
        # Refresh Active Connections
        self._do_refresh_connections()

    def _build_connections_tab(self):
        page_scroll = Gtk.ScrolledWindow()
        page_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        page_scroll.get_style_context().add_class("view")
        
        viewport = Gtk.Viewport()
        viewport.set_shadow_type(Gtk.ShadowType.NONE)
        viewport.get_style_context().add_class("view")
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        viewport.add(box)
        page_scroll.add(viewport)
        
        # --- Top: Active Connections ---
        header1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_conn = Gtk.Label(label="Active Connections (TCP/UDP)")
        lbl_conn.get_style_context().add_class("section-label")
        header1.pack_start(lbl_conn, False, False, 0)
        
        btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.MENU)
        btn_refresh.set_tooltip_text("Làm mới danh sách kết nối")
        btn_refresh.connect("clicked", lambda _: self._do_refresh_connections())
        header1.pack_end(btn_refresh, False, False, 0)
        
        box.pack_start(header1, False, False, 0)
        
        scroll_conn = Gtk.ScrolledWindow()
        scroll_conn.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # Giới hạn chiều cao hiển thị khoảng 10 dòng (10 * ~24px + header) = ~270px
        scroll_conn.set_size_request(-1, 270)
        box.pack_start(scroll_conn, False, False, 0)

        # Thêm cột Start và Duration
        self.conn_store = Gtk.ListStore(str, str, str, str, str, str, str, str, str)
        self.conn_tree = Gtk.TreeView(model=self.conn_store)
        self.conn_tree.set_headers_visible(True)

        for title, col_id, width in [
            ("Proto", 0, 50), ("Local IP", 1, 100), ("L.Port", 2, 60),
            ("Remote IP", 3, 100), ("R.Port", 4, 60), ("State", 5, 100), ("UID", 6, 50),
            ("Start", 7, 80), ("Duration", 8, 80)
        ]:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            self.conn_tree.append_column(col)

        scroll_conn.add(self.conn_tree)
        
        # --- Bảng Grid cho các Sessions hiện có ---
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(sep, False, False, 8)
        
        lbl_managed = Gtk.Label(label="Managed Sessions")
        lbl_managed.set_halign(Gtk.Align.START)
        lbl_managed.get_style_context().add_class("section-label")
        box.pack_start(lbl_managed, False, False, 0)
        
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(5)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_row_spacing(10)
        self.flowbox.set_column_spacing(10)
        
        # Bỏ scroll của flowbox, pack trực tiếp vào box vì đã có page_scroll
        box.pack_start(self.flowbox, False, False, 0)
        
        self.main_notebook.append_page(page_scroll, Gtk.Label(label="Connections"))

    def _build_sessions_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.session_notebook = Gtk.Notebook()
        self.session_notebook.set_scrollable(True)
        box.pack_start(self.session_notebook, True, True, 0)
        
        btn_add = Gtk.Button(label="+ Mở Session")
        btn_add.get_style_context().add_class("btn-success")
        btn_add.connect("clicked", self._on_add_session)
        btn_add.show()
        
        self.session_notebook.set_action_widget(btn_add, Gtk.PackType.END)
        
        self.main_notebook.append_page(box, Gtk.Label(label="Sessions"))
        
    def _do_refresh_connections(self):
        thread = threading.Thread(target=self._thread_refresh_conn, daemon=True)
        thread.start()
        
    def _thread_refresh_conn(self):
        try:
            result = subprocess.run(
                [self._backend, 'connections'],
                capture_output=True, text=True, timeout=5
            )
            entries = []
            for line in result.stdout.strip().split('\n'):
                if not line or line.startswith("ERROR"):
                    continue
                parts = line.split('|')
                if len(parts) >= 7:
                    entries.append((parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]))
            GLib.idle_add(self._update_conn_store, entries)
        except Exception:
            pass

    def _update_conn_store(self, entries):
        self.conn_store.clear()
        current_time = time.time()
        new_known = {}
        
        for row in entries:
            proto, lip, lport, rip, rport, state, uid = row
            key = (proto, lip, lport, rip, rport)
            
            if key in self.known_conns:
                start_time = self.known_conns[key]
            else:
                start_time = current_time
            new_known[key] = start_time
            
            # Format times
            start_str = time.strftime("%H:%M:%S", time.localtime(start_time))
            dur_secs = int(current_time - start_time)
            
            # hh:mm:ss format for duration
            if dur_secs >= 3600:
                dur_str = f"{dur_secs // 3600:02d}:{(dur_secs % 3600) // 60:02d}:{dur_secs % 60:02d}"
            else:
                dur_str = f"{dur_secs // 60:02d}:{dur_secs % 60:02d}"
                
            self.conn_store.append([proto, lip, lport, rip, rport, state, uid, start_str, dur_str])
            
        self.known_conns = new_known
            
    def _refresh_managed_sessions_ui(self):
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)

        for s_id, session in self.sessions.items():
            frame = Gtk.Frame()
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            vbox.set_border_width(8)
            vbox.get_style_context().add_class("tab-label-box")
            
            lbl_name = Gtk.Label()
            lbl_name.set_markup(f"<b>{session.session_name}</b>")
            vbox.pack_start(lbl_name, False, False, 0)
            
            lbl_proto = Gtk.Label(label=f"Proto: {session.proto}")
            vbox.pack_start(lbl_proto, False, False, 0)
            
            lbl_serv = Gtk.Label(label=f"SV: {session.server_status_text}")
            lbl_serv.get_style_context().add_class("dim-label")
            vbox.pack_start(lbl_serv, False, False, 0)
            
            lbl_cli = Gtk.Label(label=f"CL: {session.client_status_text}")
            lbl_cli.get_style_context().add_class("dim-label")
            vbox.pack_start(lbl_cli, False, False, 0)
            
            btn = Gtk.Button(label="Xem phiên này")
            btn.get_style_context().add_class("btn-primary")
            btn.connect("clicked", lambda b, sid=s_id: self._switch_to_session(sid))
            vbox.pack_start(btn, False, False, 4)
            
            frame.add(vbox)
            self.flowbox.add(frame)
        self.flowbox.show_all()

    def _switch_to_session(self, s_id):
        self.main_notebook.set_current_page(1) # Chuyển sang tab Sessions
        if s_id in self.sessions:
            session = self.sessions[s_id]
            page_num = self.session_notebook.page_num(session)
            if page_num >= 0:
                self.session_notebook.set_current_page(page_num)

    def _on_add_session(self, widget) -> None:
        toplevel = self.get_toplevel()
        next_id = 1
        used_ids = set(self.sessions.keys())
        while next_id in used_ids:
            next_id += 1
            
        default_name = f"Session {next_id}"
        dialog = SocketCreateDialog(toplevel, default_name)
        response = dialog.run()
        
        if response == Gtk.ResponseType.OK:
            data = dialog.get_data()
            if data["name"]:
                self._create_session(next_id, data)
                
        dialog.destroy()

    def _create_session(self, s_id, data):
        session = SocketSession(s_id, data["name"], data["proto"], self._refresh_managed_sessions_ui)
        self.sessions[s_id] = session
        
        label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        label_box.get_style_context().add_class("tab-label-box")
        label = Gtk.Label(label=data["name"])
        btn_close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        btn_close.set_relief(Gtk.ReliefStyle.NONE)
        
        label_box.set_can_focus(False)
        label.set_can_focus(False)
        btn_close.set_can_focus(False)
        
        label_box.pack_start(label, True, True, 0)
        label_box.pack_start(btn_close, False, False, 0)
        label_box.show_all()
        
        page_num = self.session_notebook.append_page(session, label_box)
        session.show_all()
        self.session_notebook.set_current_page(page_num)
        
        btn_close.connect("clicked", self._on_close_session, session, s_id)
        self._refresh_managed_sessions_ui()

    def _on_close_session(self, button, session, s_id) -> None:
        page_num = self.session_notebook.page_num(session)
        if page_num >= 0:
            session.cleanup()
            self.session_notebook.remove_page(page_num)
            
        if s_id in self.sessions:
            del self.sessions[s_id]
            
        self._reindex_sessions()
        self._refresh_managed_sessions_ui()

    def _reindex_sessions(self):
        """Đổi tên lại các session mặc định để số thứ tự liền mạch."""
        import re
        sorted_ids = sorted(self.sessions.keys())
        for new_idx, old_id in enumerate(sorted_ids, start=1):
            session = self.sessions[old_id]
            if re.match(r'^Session \d+$', session.session_name):
                new_name = f"Session {new_idx}"
                if session.session_name != new_name:
                    session.session_name = new_name
                    page_num = self.session_notebook.page_num(session)
                    if page_num >= 0:
                        lbl_box = self.session_notebook.get_tab_label(session)
                        if lbl_box:
                            lbl = lbl_box.get_children()[0]
                            lbl.set_text(new_name)

    def cleanup(self) -> None:
        for s_id, session in self.sessions.items():
            session.cleanup()

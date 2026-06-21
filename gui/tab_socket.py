"""
tab_socket.py — Tab TCP Socket Chat (Server + Client trong cùng 1 cửa sổ).
Fix layout ngang hàng, chia chat log thành 2 ô, fix duplicate messages.
"""

import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from utils.helpers import get_backend_path, format_time


class TabSocket(Gtk.Box):
    """
    Tab Socket TCP Chat:
    - F3.1: Khởi động TCP server (bind 0.0.0.0)
    - F3.2: Kết nối TCP client (IP bất kỳ)
    - F3.3: Gửi message (không duplicate)
    - F3.4: Nhận message real-time (chia 2 ô log)
    - F3.5: Hiển thị trạng thái kết nối (badge)
    - F3.6: Ngắt kết nối
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_border_width(12)

        self._server_proc = None
        self._client_proc = None
        self._server_thread = None
        self._client_thread = None
        self._server_connected = False
        self._client_connected = False

        self._build_ui()

    def _build_ui(self) -> None:
        """Xây dựng giao diện tab Socket."""

        # === Server + Client panels (cạnh nhau, homogeneous) ===
        panels = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        panels.set_homogeneous(True)  # Đảm bảo 2 panel bằng nhau
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

        # Sử dụng pack_end để nút luôn nằm ở dưới cùng, đồng bộ với Client
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

        # Server log (bên trái)
        scroll_server_log = Gtk.ScrolledWindow()
        scroll_server_log.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_server_log.get_style_context().add_class("chat-log")
        self.server_log_view = Gtk.TextView()
        self.server_log_view.set_editable(False)
        self.server_log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll_server_log.add(self.server_log_view)
        chat_paned.pack1(scroll_server_log, True, True)

        # Client log (bên phải)
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
        """Khởi động TCP server."""
        if self._server_proc:
            self._append_server_log("⚠ Server đang chạy rồi.")
            return

        port = self.entry_server_port.get_text().strip()
        if not port:
            self._append_server_log("⚠ Vui lòng nhập port.")
            return

        backend = get_backend_path("socket_server")
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

            self._update_server_status("waiting")

        except FileNotFoundError:
            self._append_server_log("❌ Không tìm thấy backend/socket_server. Hãy chạy 'make'.")
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
                        GLib.idle_add(self._update_server_status, "waiting")
                        GLib.idle_add(self._append_server_log, "🔄 Server đang chờ kết nối...")
                    elif status == "CONNECTED":
                        client_ip = parts[2] if len(parts) > 2 else "unknown"
                        self._server_connected = True
                        GLib.idle_add(self._update_server_status, "connected")
                        GLib.idle_add(self._append_server_log, f"✅ Client đã kết nối từ {client_ip}")
                    elif status == "DISCONNECTED":
                        self._server_connected = False
                        GLib.idle_add(self._update_server_status, "disconnected")
                        GLib.idle_add(self._append_server_log, "❌ Client đã ngắt kết nối.")
                elif line.startswith("RECV|"):
                    msg = line.split("|", 1)[1]
                    ts = format_time()
                    # Nhận từ client → log vào server log
                    GLib.idle_add(self._append_server_log, f"[{ts}] ← [CLIENT]: {msg}")
                elif line.startswith("ERROR|"):
                    GLib.idle_add(self._append_server_log, f"❌ {line.split('|', 1)[1]}")
        except Exception:
            pass

    # ─── Client ──────────────────────────────────────────────

    def _on_connect_client(self, button: Gtk.Button) -> None:
        """Kết nối TCP client tới server."""
        if self._client_proc:
            self._append_client_log("⚠ Client đang kết nối rồi.")
            return

        host = self.entry_client_host.get_text().strip()
        port = self.entry_client_port.get_text().strip()
        if not host or not port:
            self._append_client_log("⚠ Vui lòng nhập host và port.")
            return

        backend = get_backend_path("socket_client")
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

            self._update_client_status("waiting")

        except FileNotFoundError:
            self._append_client_log("❌ Không tìm thấy backend/socket_client. Hãy chạy 'make'.")
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
                        GLib.idle_add(self._update_client_status, "connected")
                        GLib.idle_add(self._append_client_log, "✅ Đã kết nối tới server.")
                    elif status == "DISCONNECTED":
                        self._client_connected = False
                        GLib.idle_add(self._update_client_status, "disconnected")
                        GLib.idle_add(self._append_client_log, "❌ Đã mất kết nối với server.")
                elif line.startswith("RECV|"):
                    msg = line.split("|", 1)[1]
                    ts = format_time()
                    # Nhận từ server → log vào client log
                    GLib.idle_add(self._append_client_log, f"[{ts}] ← [SERVER]: {msg}")
                elif line.startswith("ERROR|"):
                    GLib.idle_add(self._append_client_log, f"❌ {line.split('|', 1)[1]}")
                    GLib.idle_add(self._update_client_status, "disconnected")
        except Exception:
            pass

    # ─── Gửi message ─────────────────────────────────────────

    def _on_send_message(self, widget) -> None:
        """Gửi message qua stdin của server hoặc client process.
        CHỈ log vào ô log tương ứng bên gửi 1 lần (fix duplicate)."""
        msg = self.entry_msg.get_text().strip()
        if not msg:
            return

        ts = format_time()

        if self.radio_server.get_active():
            # Gửi từ server
            if not self._server_proc or not self._server_connected:
                self._append_server_log("⚠ Server chưa có client kết nối.")
                return
            try:
                self._server_proc.stdin.write(msg + "\n")
                self._server_proc.stdin.flush()
                # Log vào ô SERVER (chỉ 1 lần — không echo từ backend)
                self._append_server_log(f"[{ts}] → [GỬI]: {msg}")
            except Exception as e:
                self._append_server_log(f"❌ Lỗi gửi từ server: {e}")
        else:
            # Gửi từ client
            if not self._client_proc or not self._client_connected:
                self._append_client_log("⚠ Client chưa kết nối.")
                return
            try:
                self._client_proc.stdin.write(msg + "\n")
                self._client_proc.stdin.flush()
                # Log vào ô CLIENT (chỉ 1 lần — không echo từ backend)
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
            self._update_server_status("disconnected")

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
            self._update_client_status("disconnected")

    # ─── UI helpers ──────────────────────────────────────────

    def _append_server_log(self, text: str) -> None:
        """Thêm dòng vào server log."""
        buf = self.server_log_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        mark = buf.get_insert()
        self.server_log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _append_client_log(self, text: str) -> None:
        """Thêm dòng vào client log."""
        buf = self.client_log_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        mark = buf.get_insert()
        self.client_log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _update_server_status(self, status: str) -> None:
        """Cập nhật badge trạng thái server."""
        ctx = self.lbl_server_status.get_style_context()
        ctx.remove_class("status-connected")
        ctx.remove_class("status-disconnected")
        ctx.remove_class("status-waiting")

        if status == "connected":
            self.lbl_server_status.set_text("✅ Đã kết nối")
            ctx.add_class("status-connected")
        elif status == "waiting":
            self.lbl_server_status.set_text("🔄 Đang chờ kết nối")
            ctx.add_class("status-waiting")
        else:
            self.lbl_server_status.set_text("❌ Chưa khởi động")
            ctx.add_class("status-disconnected")

    def _update_client_status(self, status: str) -> None:
        """Cập nhật badge trạng thái client."""
        ctx = self.lbl_client_status.get_style_context()
        ctx.remove_class("status-connected")
        ctx.remove_class("status-disconnected")
        ctx.remove_class("status-waiting")

        if status == "connected":
            self.lbl_client_status.set_text("✅ Đã kết nối")
            ctx.add_class("status-connected")
        elif status == "waiting":
            self.lbl_client_status.set_text("🔄 Đang kết nối...")
            ctx.add_class("status-waiting")
        else:
            self.lbl_client_status.set_text("❌ Chưa kết nối")
            ctx.add_class("status-disconnected")

    # ─── Cleanup ─────────────────────────────────────────────

    def cleanup(self) -> None:
        """Cleanup khi đóng app."""
        self._stop_server()
        self._stop_client()

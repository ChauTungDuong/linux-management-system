"""
tab_process.py — Tab quản lý tiến trình (Process Manager).
Sub-tabs (Tất cả / Hệ thống / Người dùng), thanh tìm kiếm, live refresh,
command output log hiển thị PID, và chế độ tree view.
"""

import os
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from utils.helpers import get_backend_path, format_mem_kb


class TabProcess(Gtk.Box):
    """
    Tab quản lý tiến trình:
    - Sub-tabs: Tất cả / Hệ thống / Người dùng
    - Thanh tìm kiếm theo PID / Tên
    - Auto-refresh mỗi 1 giây (live top-like)
    - Tạo tiến trình con (fork + exec) với output log
    - Gửi signal (SIGTERM/SIGKILL/SIGSTOP/SIGCONT)
    - Kill trực tiếp
    - Xem process tree (TreeView + TreeStore)
    """

    # Mapping signal name → signal number
    SIGNALS = {
        "SIGHUP (1)": 1,
        "SIGINT (2)": 2,
        "SIGQUIT (3)": 3,
        "SIGKILL (9)": 9,
        "SIGUSR1 (10)": 10,
        "SIGUSR2 (12)": 12,
        "SIGTERM (15)": 15,
        "SIGCONT (18)": 18,
        "SIGSTOP (19)": 19,
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_border_width(12)

        self._auto_refresh = True
        self._timer_id = None
        self._backend = get_backend_path("process_mgr")
        self._show_tree = False  # Toggle giữa list và tree view
        self._search_text = ""
        self._current_uid = os.getuid()
        self._all_entries = []  # Cache dữ liệu mới nhất
        self._created_procs = {}  # PID -> subprocess.Popen for command output tracking

        self._build_ui()
        self._start_auto_refresh()

    def _build_ui(self) -> None:
        """Xây dựng toàn bộ giao diện tab."""

        # === Toolbar: Auto-refresh + Search + Tree toggle ===
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_border_width(0)
        toolbar.set_margin_bottom(8)
        self.pack_start(toolbar, False, False, 0)

        lbl = Gtk.Label(label="Tự động làm mới:")
        lbl.get_style_context().add_class("metadata-label")
        toolbar.pack_start(lbl, False, False, 0)

        self.switch_refresh = Gtk.Switch()
        self.switch_refresh.set_active(True)
        self.switch_refresh.set_valign(Gtk.Align.CENTER)
        self.switch_refresh.connect("notify::active", self._on_toggle_refresh)
        toolbar.pack_start(self.switch_refresh, False, False, 0)

        lbl2 = Gtk.Label(label="1s")
        lbl2.get_style_context().add_class("metadata-label")
        toolbar.pack_start(lbl2, False, False, 0)

        # Summary label
        self.lbl_summary = Gtk.Label(label="0 tiến trình")
        self.lbl_summary.get_style_context().add_class("summary-bar")
        toolbar.pack_start(self.lbl_summary, False, False, 4)

        # Thanh tìm kiếm
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Tìm theo tên hoặc PID...")
        self.search_entry.set_width_chars(30)
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.connect("search-changed", self._on_search_changed)
        toolbar.pack_start(self.search_entry, False, False, 4)

        # Nút chuyển đổi List / Tree
        self.btn_toggle_tree = Gtk.Button(label="Cây tiến trình")
        self.btn_toggle_tree.connect("clicked", self._on_toggle_tree)
        toolbar.pack_end(self.btn_toggle_tree, False, False, 0)
        
        # Nút Mở rộng / Thu gọn cây (ẩn mặc định, chỉ hiện ở chế độ Cây)
        self.btn_expand_tree = Gtk.Button(label="Mở rộng tất cả")
        self.btn_expand_tree.connect("clicked", self._on_expand_tree)
        self.btn_expand_tree.set_no_show_all(True)
        toolbar.pack_end(self.btn_expand_tree, False, False, 4)

        # Nút refresh thủ công
        btn_refresh = Gtk.Button(label="Làm mới")
        btn_refresh.connect("clicked", lambda _: self._refresh_data())
        toolbar.pack_end(btn_refresh, False, False, 4)

        # === Sub-notebook: Tất cả / Hệ thống / Người dùng ===
        self.sub_notebook = Gtk.Notebook()
        self.sub_notebook.connect("switch-page", self._on_sub_tab_changed)
        self.pack_start(self.sub_notebook, True, True, 0)

        # Tab "Tất cả"
        self._build_sub_tab("all", "Tất cả")
        # Tab "Hệ thống"
        self._build_sub_tab("system", "Hệ thống")
        # Tab "Người dùng"
        self._build_sub_tab("user", "Người dùng")

        # === Stack cho Tree view (chung) ===
        self.tree_scroll = Gtk.ScrolledWindow()
        self.tree_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.tree_store = Gtk.TreeStore(int, str, str)
        self.tree_treeview = Gtk.TreeView(model=self.tree_store)
        self.tree_treeview.set_headers_visible(True)
        self.tree_treeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.tree_treeview.connect("row-activated", self._on_row_activated)

        for title, col_id, width in [("PID", 0, 100), ("Tên tiến trình", 1, 250), ("Trạng thái", 2, 120)]:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            self.tree_treeview.append_column(col)

        self.tree_scroll.add(self.tree_treeview)
        # Tree view not shown initially

        # === Panel điều khiển (phía dưới) ===
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        controls.set_margin_top(8)
        self.pack_start(controls, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        controls.pack_start(sep, False, False, 2)

        # SizeGroup để căn lề Lệnh mới và Signal
        sg = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        # Dòng 1: Tạo tiến trình
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row1.set_margin_top(4)
        controls.pack_start(row1, False, False, 0)

        lbl_cmd = Gtk.Label(label="Lệnh mới:")
        lbl_cmd.set_xalign(0.0)
        lbl_cmd.get_style_context().add_class("metadata-label")
        sg.add_widget(lbl_cmd)
        row1.pack_start(lbl_cmd, False, False, 0)
        self.entry_cmd = Gtk.Entry()
        self.entry_cmd.set_placeholder_text("Nhập lệnh (ví dụ: sleep 30)")
        self.entry_cmd.set_hexpand(True)
        self.entry_cmd.connect("activate", lambda _: self._on_create_process(None))
        row1.pack_start(self.entry_cmd, True, True, 0)

        btn_create = Gtk.Button(label="Tạo tiến trình")
        btn_create.get_style_context().add_class("btn-success")
        btn_create.connect("clicked", self._on_create_process)
        row1.pack_start(btn_create, False, False, 0)

        btn_zombie = Gtk.Button(label="Tạo Zombie")
        btn_zombie.get_style_context().add_class("btn-warning")
        btn_zombie.connect("clicked", self._on_create_zombie)
        row1.pack_start(btn_zombie, False, False, 0)

        btn_fork = Gtk.Button(label="Test Fork")
        btn_fork.get_style_context().add_class("btn-info")
        btn_fork.connect("clicked", self._on_create_fork)
        row1.pack_start(btn_fork, False, False, 0)

        # Dòng 2: Signal
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        controls.pack_start(row2, False, False, 0)

        lbl_sig = Gtk.Label(label="Signal:")
        lbl_sig.set_xalign(0.0)
        lbl_sig.get_style_context().add_class("metadata-label")
        sg.add_widget(lbl_sig)
        row2.pack_start(lbl_sig, False, False, 0)
        self.combo_signal = Gtk.ComboBoxText()
        for sig_name in self.SIGNALS:
            self.combo_signal.append_text(sig_name)
        self.combo_signal.set_active(0)
        row2.pack_start(self.combo_signal, False, False, 0)

        btn_signal = Gtk.Button(label="Gửi signal")
        btn_signal.connect("clicked", self._on_send_signal)
        row2.pack_start(btn_signal, False, False, 0)

        btn_kill = Gtk.Button(label="Kill")
        btn_kill.get_style_context().add_class("btn-danger")
        btn_kill.connect("clicked", self._on_kill_process)
        row2.pack_start(btn_kill, False, False, 0)

        # === Output log (command output) ===
        lbl_output = Gtk.Label(label="Output log:")
        lbl_output.set_halign(Gtk.Align.START)
        lbl_output.get_style_context().add_class("metadata-label")
        controls.pack_start(lbl_output, False, False, 0)

        scroll_out = Gtk.ScrolledWindow()
        scroll_out.set_size_request(-1, 110)
        scroll_out.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_out.get_style_context().add_class("output-panel")
        controls.pack_start(scroll_out, False, True, 0)

        self.output_view = Gtk.TextView()
        self.output_view.set_editable(False)
        self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll_out.add(self.output_view)

    def _build_sub_tab(self, name: str, label: str) -> None:
        """Xây dựng một sub-tab với bảng tiến trình."""
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # ListStore: PID(int), Name(str), CPU%(str), MEM(str), State(str), UID(int)
        store = Gtk.ListStore(int, str, str, str, str, int)
        treeview = Gtk.TreeView(model=store)
        treeview.set_headers_visible(True)
        treeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        treeview.connect("row-activated", self._on_row_activated)

        columns = [
            ("PID", 0, 80),
            ("Tên tiến trình", 1, 200),
            ("CPU%", 2, 80),
            ("MEM", 3, 100),
            ("Trạng thái", 4, 120),
        ]
        for title, col_id, width in columns:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=col_id)
            col.set_resizable(True)
            col.set_min_width(width)
            col.set_sort_column_id(col_id)
            treeview.append_column(col)

        scroll.add(treeview)
        self.sub_notebook.append_page(scroll, Gtk.Label(label=label))

        # Lưu tham chiếu
        setattr(self, f"_store_{name}", store)
        setattr(self, f"_treeview_{name}", treeview)

    # ─── Auto-refresh ────────────────────────────────────────

    def _start_auto_refresh(self) -> None:
        """Bắt đầu timer auto-refresh mỗi 1 giây."""
        self._refresh_data()
        self._timer_id = GLib.timeout_add(1000, self._on_timer)

    def _on_timer(self) -> bool:
        """Callback timer — refresh nếu auto-refresh ON."""
        if self._auto_refresh:
            self._refresh_data()
        return True  # Tiếp tục timer

    def _on_toggle_refresh(self, switch: Gtk.Switch, gparam) -> None:
        """Toggle auto-refresh ON/OFF."""
        self._auto_refresh = switch.get_active()

    def _on_toggle_tree(self, button: Gtk.Button) -> None:
        """Chuyển đổi giữa list view và tree view."""
        self._show_tree = not self._show_tree
        if self._show_tree:
            button.set_label("Danh sách")
            self.btn_expand_tree.show()
            self.btn_expand_tree.set_label("Mở rộng tất cả")
            # Ẩn sub_notebook, hiện tree view
            self.sub_notebook.hide()
            self.tree_scroll.show_all()
            # Chèn tree_scroll vào vị trí sub_notebook nếu chưa có
            if self.tree_scroll.get_parent() is None:
                self.pack_start(self.tree_scroll, True, True, 0)
                self.reorder_child(self.tree_scroll, 2)  # Sau toolbar & search
            self._refresh_tree()
        else:
            button.set_label("Cây tiến trình")
            self.btn_expand_tree.hide()
            self.tree_scroll.hide()
            self.sub_notebook.show_all()
            self._refresh_data()

    def _on_expand_tree(self, button: Gtk.Button) -> None:
        """Bung / Thu gọn toàn bộ cây tiến trình."""
        if button.get_label() == "Mở rộng tất cả":
            self.tree_treeview.expand_all()
            button.set_label("Thu gọn tất cả")
        else:
            self.tree_treeview.collapse_all()
            if self.tree_store.get_iter_first():
                self.tree_treeview.expand_to_path(Gtk.TreePath.new_from_string("0"))
            button.set_label("Mở rộng tất cả")

    def _on_sub_tab_changed(self, notebook, page, page_num) -> None:
        """Khi chuyển sub-tab, cập nhật hiển thị."""
        self._update_all_stores()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Lọc tiến trình khi thay đổi text tìm kiếm."""
        self._search_text = entry.get_text().strip().lower()
        self._update_all_stores()
        if getattr(self, "_show_tree", False):
            self._refresh_tree()

    def _on_row_activated(self, treeview: Gtk.TreeView, path: Gtk.TreePath, column: Gtk.TreeViewColumn) -> None:
        """Kích hoạt khi double-click vào một tiến trình."""
        model = treeview.get_model()
        treeiter = model.get_iter(path)
        pid = model[treeiter][0]
        
        cached_entry = None
        for entry in self._all_entries:
            if entry[0] == pid:
                cached_entry = entry
                break
                
        thread = threading.Thread(target=self._do_fetch_detail, args=(pid, cached_entry), daemon=True)
        thread.start()

    def _do_fetch_detail(self, pid: int, cached_entry: tuple) -> None:
        """Thread phụ: lấy chi tiết tiến trình."""
        try:
            result = subprocess.run(
                [self._backend, 'detail', str(pid)],
                capture_output=True, text=True, timeout=3
            )
            output = result.stdout.strip()
            if output.startswith("DETAIL|"):
                parts = output.split("|")
                name = parts[1]
                state = parts[2]
                ppid = parts[3]
                threads = parts[4]
                cmdline = parts[5] if len(parts) > 5 else ""
                GLib.idle_add(self._show_detail_dialog, pid, name, state, ppid, threads, cmdline, cached_entry)
            elif output.startswith("ERROR|"):
                GLib.idle_add(self._append_output, f"Lỗi chi tiết: {output.split('|', 1)[1]}")
        except Exception as e:
            GLib.idle_add(self._append_output, f"Lỗi fetch detail: {e}")

    def _show_detail_dialog(self, pid: int, name: str, state: str, ppid: str, threads: str, cmdline: str, cached_entry: tuple) -> None:
        """Hiển thị cửa sổ chi tiết tiến trình (Gtk.Window)."""
        import pwd
        cpu = mem = "N/A"
        uid_str = "N/A"
        user_name = "Unknown"
        if cached_entry:
            # entry: (pid, name, cpu, mem, state, uid)
            cpu = cached_entry[2]
            mem = cached_entry[3]
            uid = cached_entry[5]
            uid_str = str(uid)
            try:
                if uid >= 0:
                    user_name = pwd.getpwuid(uid).pw_name
            except Exception:
                pass
                
        window = Gtk.Window(title=f"Chi tiết tiến trình: {name}")
        window.set_transient_for(self.get_toplevel())
        window.set_modal(False)
        window.set_default_size(550, 380)
        window.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        window.set_border_width(12)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        window.add(vbox)
        
        # Header
        header = Gtk.Label()
        header.set_markup(f"<big><b>PID: {pid} — {name}</b></big>")
        header.set_halign(Gtk.Align.START)
        vbox.pack_start(header, False, False, 0)
        
        vbox.pack_start(Gtk.Separator(), False, False, 0)
        
        # Grid cho thông tin
        grid = Gtk.Grid()
        grid.set_column_spacing(24)
        grid.set_row_spacing(8)
        vbox.pack_start(grid, False, False, 0)
        
        info = [
            ("Trạng thái:", state, 0, 0),
            ("PPID:", ppid, 1, 0),
            ("Người dùng:", f"{user_name} (UID: {uid_str})", 0, 1),
            ("Số luồng:", threads, 1, 1),
            ("Sử dụng CPU:", cpu, 0, 2),
            ("Sử dụng RAM:", mem, 1, 2)
        ]
        
        for label_text, value_text, col, row in info:
            lbl_title = Gtk.Label(label=label_text)
            lbl_title.set_halign(Gtk.Align.START)
            lbl_title.get_style_context().add_class("dim-label")
            
            lbl_val = Gtk.Label(label=value_text)
            lbl_val.set_halign(Gtk.Align.START)
            lbl_val.set_selectable(True)
            
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.pack_start(lbl_title, False, False, 0)
            box.pack_start(lbl_val, False, False, 0)
            grid.attach(box, col, row, 1, 1)
            
        vbox.pack_start(Gtk.Separator(), False, False, 0)
        
        lbl_cmd = Gtk.Label(label="Command Line:")
        lbl_cmd.set_halign(Gtk.Align.START)
        lbl_cmd.get_style_context().add_class("dim-label")
        vbox.pack_start(lbl_cmd, False, False, 0)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(scroll, True, True, 0)
        
        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.get_buffer().set_text(cmdline)
        scroll.add(tv)
        
        bbox = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        bbox.set_layout(Gtk.ButtonBoxStyle.END)
        vbox.pack_end(bbox, False, False, 0)
        
        btn_close = Gtk.Button(label="Đóng")
        btn_close.connect("clicked", lambda w: window.destroy())
        bbox.add(btn_close)
        
        window.show_all()

    # ─── Data refresh (chạy trong thread phụ) ────────────────

    def _refresh_data(self) -> None:
        """Gọi backend 'list' trong thread phụ, update UI qua GLib.idle_add."""
        thread = threading.Thread(target=self._do_refresh_list, daemon=True)
        thread.start()

    def _do_refresh_list(self) -> None:
        """Thread phụ: gọi process_mgr list, parse output."""
        try:
            result = subprocess.run(
                [self._backend, 'list'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                GLib.idle_add(self._append_output, f"Lỗi: {result.stderr}")
                return

            entries = []
            for line in result.stdout.strip().split('\n'):
                if not line: continue
                parts = line.split('|')
                if len(parts) >= 6:
                    pid = int(parts[0])
                    name = parts[1]
                    cpu = f"{float(parts[2]):.1f}%"
                    mem = format_mem_kb(int(parts[3]))
                    state_map = {'R': 'R (running)', 'S': 'S (sleeping)',
                                 'Z': 'Z (zombie)', 'T': 'T (stopped)',
                                 'D': 'D (disk sleep)', 'I': 'I (idle)'}
                    state = state_map.get(parts[4], parts[4])
                    uid = int(parts[5]) if parts[5].lstrip('-').isdigit() else -1
                    entries.append((pid, name, cpu, mem, state, uid))

            GLib.idle_add(self._update_entries, entries)

        except subprocess.TimeoutExpired:
            GLib.idle_add(self._append_output, "Timeout khi lấy danh sách tiến trình")
        except FileNotFoundError:
            GLib.idle_add(self._append_output,
                          "Không tìm thấy backend/process_mgr. Hãy chạy 'make' trước.")
        except Exception as e:
            GLib.idle_add(self._append_output, f"Lỗi: {e}")

    def _update_entries(self, entries: list) -> None:
        """Cache entries và cập nhật tất cả stores."""
        self._all_entries = entries
        self._update_all_stores()
        # Cập nhật summary
        self.lbl_summary.set_text(f"{len(entries)} tiến trình")

    def _update_all_stores(self) -> None:
        """Cập nhật ListStore cho tất cả sub-tabs dựa trên filter."""
        entries = self._all_entries
        search = self._search_text

        for tab_name, filter_fn in [
            ("all", lambda e: True),
            ("system", lambda e: e[5] >= 0 and e[5] < 1000),
            ("user", lambda e: e[0] in self._created_procs),
        ]:
            store = getattr(self, f"_store_{tab_name}", None)
            treeview = getattr(self, f"_treeview_{tab_name}", None)
            if not store or not treeview:
                continue

            # Lưu selection hiện tại
            sel = treeview.get_selection()
            model, treeiter = sel.get_selected()
            selected_pid = model[treeiter][0] if treeiter else -1

            # Lưu scroll position
            vadj = treeview.get_parent().get_vadjustment() if treeview.get_parent() else None
            scroll_val = vadj.get_value() if vadj else 0

            store.clear()
            new_iter = None
            for entry in entries:
                if not filter_fn(entry):
                    continue
                # Áp dụng search filter
                if search:
                    if search.isdigit():
                        if search not in str(entry[0]):
                            continue
                    else:
                        if search not in entry[1].lower():
                            continue
                it = store.append(list(entry))
                # Khôi phục selection
                if entry[0] == selected_pid:
                    new_iter = it

            # Khôi phục selection
            if new_iter:
                sel.select_iter(new_iter)

            # Khôi phục scroll position
            if vadj:
                GLib.idle_add(vadj.set_value, scroll_val)

    def _refresh_tree(self) -> None:
        """Gọi backend 'tree' trong thread phụ."""
        thread = threading.Thread(target=self._do_refresh_tree, daemon=True)
        thread.start()

    def _do_refresh_tree(self) -> None:
        """Thread phụ: gọi process_mgr tree, parse PID|PPID|NAME."""
        try:
            result = subprocess.run(
                [self._backend, 'tree'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                GLib.idle_add(self._append_output, f"Lỗi tree: {result.stderr}")
                return

            # Parse: PID|PPID|NAME
            processes = {}
            for line in result.stdout.strip().split('\n'):
                if not line: continue
                parts = line.split('|')
                if len(parts) >= 3:
                    pid = int(parts[0])
                    ppid = int(parts[1])
                    name = parts[2]
                    processes[pid] = (ppid, name)

            GLib.idle_add(self._update_tree_store, processes)

        except Exception as e:
            GLib.idle_add(self._append_output, f"Lỗi tree: {e}")

    def _update_tree_store(self, processes: dict) -> None:
        """Xây dựng TreeStore hierarchical từ dữ liệu PID → (PPID, name)."""
        self.tree_store.clear()

        # Xây dựng mapping: parent → children
        children_map = {}
        for pid, (ppid, name) in processes.items():
            if ppid not in children_map:
                children_map[ppid] = []
            children_map[ppid].append(pid)

        search = self._search_text
        
        # Hàm đệ quy kiểm tra xem node này hoặc con cháu của nó có khớp search không
        match_memo = {}
        def matches_search(pid: int) -> bool:
            if pid in match_memo:
                return match_memo[pid]
            if pid not in processes:
                match_memo[pid] = False
                return False
                
            ppid, name = processes[pid]
            is_match = False
            
            if not search:
                is_match = True
            elif search.isdigit():
                if search in str(pid):
                    is_match = True
            else:
                if search in name.lower():
                    is_match = True
            
            # Nếu node này không khớp, kiểm tra con cháu
            if not is_match and pid in children_map:
                for child_pid in children_map[pid]:
                    if matches_search(child_pid):
                        is_match = True
                        break
                        
            match_memo[pid] = is_match
            return is_match

        iters_map = {}  # PID → TreeIter

        def add_node(pid: int, parent_iter):
            """Đệ quy thêm node vào TreeStore."""
            if pid not in processes:
                return
                
            # Nếu đang có search text và nhánh này không có kết quả nào khớp -> bỏ qua
            if search and not matches_search(pid):
                return
                
            ppid, name = processes[pid]
            
            # Lấy state từ cache entries nếu có
            state = ""
            for e in self._all_entries:
                if e[0] == pid:
                    state = e[4]
                    break
                    
            it = self.tree_store.append(parent_iter, [pid, name, state])
            iters_map[pid] = it
            
            # Thêm children
            if pid in children_map:
                for child_pid in sorted(children_map[pid]):
                    add_node(child_pid, it)

        # Thêm root processes
        roots = []
        for pid, (ppid, name) in processes.items():
            if ppid == 0 or ppid not in processes:
                roots.append(pid)

        for pid in sorted(roots):
            add_node(pid, None)

        # Expand behavior
        if search:
            self.tree_treeview.expand_all()
        elif self.tree_store.get_iter_first():
            self.tree_treeview.expand_to_path(Gtk.TreePath.new_from_string("0"))

    # ─── Tạo tiến trình ──────────────────────────────────────

    def _on_create_process(self, button) -> None:
        """Tạo tiến trình con từ lệnh nhập."""
        cmd = self.entry_cmd.get_text().strip()
        if not cmd:
            self._append_output("⚠ Vui lòng nhập lệnh cần chạy.")
            return

        parts = cmd.split()
        self.entry_cmd.set_text("")
        thread = threading.Thread(
            target=self._do_create_process, args=(parts,), daemon=True)
        thread.start()

    def _do_create_process(self, parts: list) -> None:
        """Thread phụ: tạo tiến trình bằng subprocess.Popen và stream output."""
        from utils.helpers import format_time
        ts = format_time()
        try:
            proc = subprocess.Popen(
                parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            pid = proc.pid
            self._created_procs[pid] = proc
            GLib.idle_add(self._append_output,
                          f"[{ts}] ✅ Đã tạo tiến trình: PID {pid} — lệnh: {' '.join(parts)}")
            GLib.idle_add(self._update_status, f"Đã tạo tiến trình PID {pid}")

            # Stream output real-time
            if proc.stdout:
                for line in proc.stdout:
                    GLib.idle_add(self._append_output,
                                  f"  [{pid}] {line.rstrip()}")

            proc.wait()
            exit_code = proc.returncode
            ts2 = format_time()
            GLib.idle_add(self._append_output,
                          f"[{ts2}] [{pid}] Kết thúc (exit code: {exit_code})")

        except FileNotFoundError:
            GLib.idle_add(self._append_output,
                          f"[{ts}] ❌ Lệnh không tồn tại: {parts[0]}")
        except Exception as e:
            GLib.idle_add(self._append_output, f"[{ts}] ❌ Lỗi tạo tiến trình: {e}")

    def _on_create_zombie(self, button) -> None:
        """Tạo tiến trình zombie thông qua backend."""
        self.entry_cmd.set_text("")
        thread = threading.Thread(
            target=self._do_create_process_backend, args=(["zombie"], "Tạo Zombie"), daemon=True)
        thread.start()

    def _on_create_fork(self, button) -> None:
        """Tạo tiến trình con (fork test) thông qua backend."""
        self.entry_cmd.set_text("")
        thread = threading.Thread(
            target=self._do_create_process_backend, args=(["fork_test"], "Test Fork"), daemon=True)
        thread.start()

    def _do_create_process_backend(self, parts: list, action_name: str) -> None:
        """Thread phụ: chạy lệnh backend đặc biệt (zombie, fork_test)."""
        from utils.helpers import format_time
        ts = format_time()
        try:
            cmd = [self._backend] + parts
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            GLib.idle_add(self._append_output,
                          f"[{ts}] ⏳ Đang thực thi {action_name}...")
            
            if proc.stdout:
                for line in proc.stdout:
                    line = line.rstrip()
                    if line.startswith("CREATED|"):
                        child_pid = int(line.split("|")[1])
                        self._created_procs[child_pid] = proc
                        GLib.idle_add(self._append_output,
                                      f"[{ts}] ✅ Đã tạo: PID {child_pid} — {action_name}")
                        GLib.idle_add(self._update_status, f"Đã tạo {action_name} PID {child_pid}")
                    else:
                        GLib.idle_add(self._append_output,
                                      f"  [Backend] {line}")

            proc.wait()
            exit_code = proc.returncode
            ts2 = format_time()
            GLib.idle_add(self._append_output,
                          f"[{ts2}] {action_name} kết thúc (exit code: {exit_code})")

        except Exception as e:
            GLib.idle_add(self._append_output, f"[{ts}] ❌ Lỗi {action_name}: {e}")

    # ─── Gửi signal ──────────────────────────────────────────

    def _get_selected_pid(self) -> int:
        """Lấy PID từ dòng đang chọn (active sub-tab hoặc tree view)."""
        if self._show_tree:
            sel = self.tree_treeview.get_selection()
            model, treeiter = sel.get_selected()
        else:
            # Lấy từ sub-tab hiện tại
            page_num = self.sub_notebook.get_current_page()
            tab_names = ["all", "system", "user"]
            tab_name = tab_names[page_num] if page_num < len(tab_names) else "all"
            treeview = getattr(self, f"_treeview_{tab_name}", None)
            if not treeview:
                return -1
            sel = treeview.get_selection()
            model, treeiter = sel.get_selected()

        if treeiter is None:
            return -1
        return model[treeiter][0]  # Cột 0 = PID

    def _on_send_signal(self, button: Gtk.Button) -> None:
        """Gửi signal được chọn tới PID đang chọn."""
        pid = self._get_selected_pid()
        if pid < 0:
            self._append_output("⚠ Vui lòng chọn một tiến trình trong bảng.")
            return

        sig_text = self.combo_signal.get_active_text()
        sig_num = self.SIGNALS.get(sig_text, 15)

        thread = threading.Thread(
            target=self._do_send_signal, args=(pid, sig_num), daemon=True)
        thread.start()

    def _on_kill_process(self, button: Gtk.Button) -> None:
        """Kill ngay (SIGKILL) tiến trình đang chọn (có xác nhận)."""
        pid = self._get_selected_pid()
        if pid < 0:
            self._append_output("⚠ Vui lòng chọn một tiến trình trong bảng.")
            return

        # Lấy tên tiến trình từ bảng
        process_name = self._get_process_name_by_pid(pid)

        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Xác nhận Kill tiến trình?\n\nPID: {pid}\nTên: {process_name}\n\nHành động này không thể hoàn tác."
        )
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            thread = threading.Thread(
                target=self._do_send_signal, args=(pid, 9), daemon=True)
            thread.start()

    def _do_send_signal(self, pid: int, sig: int) -> None:
        """Thread phụ: gọi process_mgr signal."""
        try:
            result = subprocess.run(
                [self._backend, 'signal', str(pid), str(sig)],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout.strip()
            if output.startswith("OK|"):
                parts = output.split("|")
                GLib.idle_add(self._append_output,
                              f"✅ Đã gửi {parts[2]} tới PID {parts[1]}")
            elif output.startswith("ERROR|"):
                GLib.idle_add(self._append_output, f"❌ {output.split('|', 1)[1]}")
            else:
                GLib.idle_add(self._append_output, f"Output: {output}")
        except Exception as e:
            GLib.idle_add(self._append_output, f"❌ Lỗi gửi signal: {e}")

    # ─── Output log ──────────────────────────────────────────

    def _append_output(self, text: str) -> None:
        """Thêm dòng mới vào output log (thread-safe qua GLib.idle_add)."""
        buf = self.output_view.get_buffer()
        end_iter = buf.get_end_iter()
        buf.insert(end_iter, text + "\n")
        # Auto-scroll xuống cuối
        mark = buf.get_insert()
        self.output_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _get_process_name_by_pid(self, pid: int) -> str:
        """Lấy tên tiến trình từ cache entries."""
        for entry in self._all_entries:
            if entry[0] == pid:
                return entry[1]
        return "Không rõ"

    def _update_status(self, msg: str) -> None:
        """Cập nhật statusbar thông qua AppWindow."""
        try:
            toplevel = self.get_toplevel()
            if hasattr(toplevel, 'update_status'):
                toplevel.update_status(msg)
        except Exception:
            pass

    # ─── Cleanup ─────────────────────────────────────────────

    def cleanup(self) -> None:
        """Dừng timer auto-refresh khi đóng app."""
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

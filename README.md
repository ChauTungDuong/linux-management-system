# 🖥 Linux System Manager

Ứng dụng quản lý hệ thống Linux với giao diện GTK3 — demo quản lý tiến trình, file I/O, socket TCP, và thông tin mạng.

## 📋 Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Ubuntu 24.04.4 LTS (hoặc tương đương) |
| Kernel | 6.x trở lên |
| Python | >= 3.11 |
| GCC | >= 11 |
| RAM | >= 512 MB |

---

## 🔧 Hướng dẫn cài đặt

### Bước 1: Cập nhật hệ thống

```bash
sudo apt update && sudo apt upgrade -y
```

### Bước 2: Cài đặt Python 3 và pip (nếu chưa có)

```bash
# Kiểm tra phiên bản Python
python3 --version

# Cài đặt Python 3 (nếu chưa có)
sudo apt install -y python3 python3-pip
```

### Bước 3: Cài đặt GTK3 và PyGObject

```bash
# Cài đặt PyGObject (Python GTK3 bindings)
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0

# Cài đặt thư viện GTK3 development (cho backend C nếu cần)
sudo apt install -y libgtk-3-dev
```

### Bước 4: Cài đặt GCC và công cụ build

```bash
# Cài đặt GCC, Make, và thư viện C chuẩn
sudo apt install -y gcc make libc6-dev

# Kiểm tra phiên bản
gcc --version
make --version
```

### Bước 5: Cài đặt công cụ mạng (cho tab Ping)

```bash
# Cài đặt iputils-ping (thường đã có sẵn)
sudo apt install -y iputils-ping
```

### Bước 6: (Tùy chọn) Cài thêm công cụ debug

```bash
# Kiểm tra memory leak
sudo apt install -y valgrind

# Kiểm tra file hex dump
sudo apt install -y xxd
```

### Tổng hợp — Cài tất cả bằng 1 lệnh

```bash
sudo apt update && sudo apt install -y \
    python3 python3-pip \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    libgtk-3-dev \
    gcc make libc6-dev \
    iputils-ping
```

---

## 🏗 Build & Chạy

### Build backend C

```bash
cd linux_system_manager/backend
make clean && make all
```

Kiểm tra build thành công (không có warning/error):

```bash
# Chạy test nhanh
make test
```

### Chạy ứng dụng

```bash
cd linux_system_manager
python3 main.py
```

---

## 📖 Hướng dẫn sử dụng

### Tab ⚙ Tiến trình
1. Bảng tiến trình tự động cập nhật mỗi 2 giây
2. Bật/tắt auto-refresh bằng switch
3. **Tạo tiến trình**: nhập lệnh (ví dụ: `sleep 30`) → click "▶ Tạo tiến trình"
4. **Gửi signal**: chọn process trong bảng → chọn signal → click "📤 Gửi signal"
5. **Kill ngay**: chọn process → click "💀 Kill ngay" (SIGKILL)
6. **Xem cây tiến trình**: click "🌳 Xem cây tiến trình" (TreeView expand/collapse)

### Tab 📁 File I/O
1. **Chọn file**: click "📂 Chọn file" hoặc nhập đường dẫn
2. **Đọc file**: click "📖 Đọc file" → hiển thị text + hex dump
3. **Ghi file**: nhập nội dung → click "💾 Ghi file"
4. **inotify**: nhập đường dẫn → click "▶ Bắt đầu" → theo dõi thay đổi real-time
5. **mmap demo**: chọn file → click "📊 mmap demo" → so sánh hiệu năng

### Tab 🔌 Socket TCP
1. **Server**: nhập port → click "▶ Khởi động Server"
2. **Client**: nhập host + port → click "🔌 Kết nối"
3. **Chat**: chọn gửi từ Server/Client → nhập tin nhắn → click "📨 Gửi"
4. **Cross-machine**: nhập IP máy khác (ví dụ: `192.168.1.100`) thay vì `127.0.0.1`
5. **Ngắt**: click "❌ Ngắt kết nối"

### Tab 🌐 Network
1. **Interfaces**: bảng tự động hiển thị khi mở tab
2. **Ping**: nhập host/IP → click "▶ Ping" → kết quả real-time
3. **Traffic**: hiển thị bytes nhận/gửi cho mỗi interface
4. **Routing**: hiển thị bảng định tuyến
5. **Refresh**: click "🔄 Làm mới"

---

## 🗂 Cấu trúc thư mục

```
linux_system_manager/
├── main.py                  # Entry point — khởi động GTK3 app
├── gui/
│   ├── __init__.py
│   ├── app_window.py        # Cửa sổ chính + notebook tabs
│   ├── tab_process.py       # Tab quản lý tiến trình
│   ├── tab_file.py          # Tab file I/O + inotify
│   ├── tab_socket.py        # Tab TCP chat server/client
│   └── tab_network.py       # Tab thông tin mạng + ping
├── backend/
│   ├── process_mgr.c        # Quản lý tiến trình (fork, exec, signal)
│   ├── file_mgr.c           # File I/O + inotify
│   ├── socket_server.c      # TCP server
│   ├── socket_client.c      # TCP client
│   ├── network_info.c       # Thông tin network interface
│   └── Makefile             # Build tất cả file C
├── utils/
│   ├── __init__.py
│   └── helpers.py           # Hàm tiện ích
├── assets/
│   └── style.css            # GTK CSS
├── requirements.txt
└── README.md
```

---

## ⚠ Troubleshooting

### Lỗi "No module named 'gi'"
```bash
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

### Lỗi "Address already in use" khi khởi động server
```bash
# Tìm process đang chiếm port
sudo lsof -i :9999
# Kill process đó
sudo kill -9 <PID>
```

### Lỗi "Không tìm thấy backend/process_mgr"
```bash
cd backend
make clean && make all
```

### Lỗi build "fatal error: ..." khi make
```bash
sudo apt install -y libc6-dev gcc make
```

### Ứng dụng không hiển thị giao diện (headless server)
```bash
# Cần cài desktop environment hoặc X server
sudo apt install -y xfce4  # hoặc gnome-session
```

---

## 📝 Ghi chú kỹ thuật

- **Tích hợp C ↔ Python**: Các chương trình C build thành binary riêng, Python gọi qua `subprocess`
- **Thread safety**: Tất cả update GUI đều qua `GLib.idle_add()` — không block GTK main loop
- **Syscall thuần**: File I/O dùng `open()/read()/write()` (không phải `fread/fwrite`)
- **inotify**: Chạy C process nền, đọc stdout real-time trong thread Python
- **Socket**: Server bind `0.0.0.0` — hỗ trợ kết nối từ máy khác cùng mạng

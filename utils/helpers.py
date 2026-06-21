"""
helpers.py — Hàm tiện ích dùng chung cho toàn bộ ứng dụng Linux System Manager.
Bao gồm: format bytes, format time, lấy đường dẫn backend binary.
"""

import os
import time
from typing import Optional


def format_bytes(n: int) -> str:
    """
    Chuyển đổi số bytes thành chuỗi dễ đọc (B, KB, MB, GB).
    
    @param n: Số bytes cần chuyển đổi
    @return: Chuỗi đã format, ví dụ "1.23 MB"
    """
    if n < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    size = float(n)
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.2f} {units[idx]}"


def format_time(timestamp: Optional[float] = None) -> str:
    """
    Format timestamp (epoch) thành chuỗi HH:MM:SS.
    Nếu không truyền timestamp, dùng thời gian hiện tại.
    
    @param timestamp: Unix timestamp (seconds), hoặc None
    @return: Chuỗi dạng "HH:MM:SS"
    """
    if timestamp is None:
        timestamp = time.time()
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def format_datetime(timestamp: Optional[float] = None) -> str:
    """
    Format timestamp (epoch) thành chuỗi YYYY-MM-DD HH:MM:SS.
    
    @param timestamp: Unix timestamp (seconds), hoặc None
    @return: Chuỗi dạng "2025-05-10 10:32:01"
    """
    if timestamp is None:
        timestamp = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


def get_backend_path(binary_name: str) -> str:
    """
    Trả về đường dẫn tuyệt đối tới binary C trong thư mục backend/.
    Sử dụng os.path.dirname(__file__) thay vì hardcode đường dẫn.
    
    @param binary_name: Tên binary (ví dụ: "process_mgr")
    @return: Đường dẫn tuyệt đối, ví dụ "/home/user/linux_system_manager/backend/process_mgr"
    """
    # utils/ -> project root -> backend/
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "backend", binary_name)


def get_asset_path(filename: str) -> str:
    """
    Trả về đường dẫn tuyệt đối tới file trong thư mục assets/.
    
    @param filename: Tên file (ví dụ: "style.css")
    @return: Đường dẫn tuyệt đối
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "assets", filename)


def format_permissions(mode: int) -> str:
    """
    Chuyển đổi mode (integer) thành chuỗi quyền dạng -rwxr-xr-x.
    
    @param mode: Giá trị st_mode từ os.stat()
    @return: Chuỗi quyền dạng Unix
    """
    import stat
    perms = ""
    # Loại file
    if stat.S_ISDIR(mode):
        perms += "d"
    elif stat.S_ISLNK(mode):
        perms += "l"
    else:
        perms += "-"
    # Owner
    perms += "r" if mode & stat.S_IRUSR else "-"
    perms += "w" if mode & stat.S_IWUSR else "-"
    perms += "x" if mode & stat.S_IXUSR else "-"
    # Group
    perms += "r" if mode & stat.S_IRGRP else "-"
    perms += "w" if mode & stat.S_IWGRP else "-"
    perms += "x" if mode & stat.S_IXGRP else "-"
    # Others
    perms += "r" if mode & stat.S_IROTH else "-"
    perms += "w" if mode & stat.S_IWOTH else "-"
    perms += "x" if mode & stat.S_IXOTH else "-"
    return perms


def format_mem_kb(kb: int) -> str:
    """
    Format bộ nhớ từ KB thành chuỗi dễ đọc.
    
    @param kb: Số KB
    @return: Chuỗi dạng "256 MB" hoặc "32 KB"
    """
    return format_bytes(kb * 1024)

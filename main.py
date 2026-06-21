#!/usr/bin/env python3
"""
main.py — Entry point cho ứng dụng Linux System Manager.
Khởi tạo GTK3 application, load CSS, mở cửa sổ chính.
"""

import os
import sys
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from gui.app_window import AppWindow
from utils.helpers import get_asset_path


def load_css() -> None:
    """
    Load file style.css vào GTK CSS provider.
    Dùng PRIORITY_USER để ghi đè hoàn toàn theme hệ thống.
    """
    # Dùng Adwaita light làm base theme
    os.environ.setdefault("GTK_THEME", "Adwaita")

    css_path = get_asset_path("style.css")
    if not os.path.exists(css_path):
        print(f"Cảnh báo: Không tìm thấy file CSS: {css_path}", file=sys.stderr)
        return

    css_provider = Gtk.CssProvider()
    try:
        css_provider.load_from_path(css_path)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER  # Cao nhất — ghi đè mọi theme
            )
    except Exception as e:
        print(f"Lỗi load CSS: {e}", file=sys.stderr)


def main() -> None:
    """Hàm chính — khởi động ứng dụng."""
    load_css()

    window = AppWindow()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()

    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\nĐã nhận Ctrl+C, đang thoát...")
        Gtk.main_quit()


if __name__ == "__main__":
    main()

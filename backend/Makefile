# Makefile — Build tất cả backend C cho Linux System Manager
#
# Targets:
#   all     : Build tất cả binary
#   clean   : Xóa binary và object files
#   install : (Alias cho all) binary nằm tại thư mục hiện tại
#   test    : Chạy test cơ bản cho từng binary

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -g -O2

# Danh sách binary cần build
TARGETS = process_mgr file_mgr socket_server socket_client network_info

# Target mặc định: build tất cả
all: $(TARGETS)

# Process Manager — quản lý tiến trình
process_mgr: process_mgr.c
	$(CC) $(CFLAGS) -o $@ $<

# File Manager — file I/O + inotify + mmap
file_mgr: file_mgr.c
	$(CC) $(CFLAGS) -o $@ $<

# Socket Server — TCP server (cần pthread)
socket_server: socket_server.c
	$(CC) $(CFLAGS) -pthread -o $@ $<

# Socket Client — TCP client (cần pthread)
socket_client: socket_client.c
	$(CC) $(CFLAGS) -pthread -o $@ $<

# Network Info — thông tin mạng
network_info: network_info.c
	$(CC) $(CFLAGS) -o $@ $<

# Xóa tất cả binary và object files
clean:
	rm -f $(TARGETS) *.o

# Install (binary nằm tại thư mục backend/)
install: all
	@echo "Tất cả binary đã được build tại thư mục hiện tại."

# Test cơ bản — chạy từng binary với đối số test
test: all
	@echo "=== Test process_mgr ==="
	./process_mgr list | head -5
	@echo ""
	@echo "=== Test network_info interfaces ==="
	./network_info interfaces
	@echo ""
	@echo "=== Test network_info traffic ==="
	./network_info traffic
	@echo ""
	@echo "=== Test network_info route ==="
	./network_info route
	@echo ""
	@echo "=== Tất cả test cơ bản hoàn thành ==="

# Check memory leaks bằng Valgrind
check: all
	@echo "=== Chạy Valgrind kiểm tra rò rỉ bộ nhớ ==="
	valgrind --leak-check=full --error-exitcode=1 ./process_mgr list > /dev/null
	valgrind --leak-check=full --error-exitcode=1 ./network_info interfaces > /dev/null
	@echo "=== Valgrind hoàn thành (Sạch) ==="

.PHONY: all clean install test check

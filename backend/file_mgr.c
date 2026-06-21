/* Bật POSIX + XOPEN extensions — cần trước mọi #include
 * Cần thiết với -std=c11 để expose: sigaction, clock_gettime, inotify, mmap */
#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700

/*
 * file_mgr.c — Quản lý File I/O + inotify trên Linux
 * 
 * Chức năng:
 *   - read <path>          : Đọc file bằng syscall read(), output text + hex
 *   - write <path> <text>  : Ghi file bằng syscall write()
 *   - info <path>          : Hiển thị metadata (stat)
 *   - watch <path>         : inotify real-time monitoring
 *   - mmap <path>          : So sánh hiệu năng mmap vs read
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/inotify.h>
#include <sys/mman.h>
#include <time.h>
#include <ctype.h>
#include <signal.h>
#include <pwd.h>
#include <grp.h>

#define BUF_SIZE 4096
#define EVENT_SIZE (sizeof(struct inotify_event))
#define EVENT_BUF_LEN (1024 * (EVENT_SIZE + 16))
#define HEX_BYTES_PER_LINE 16

/* Flag để dừng inotify loop khi nhận SIGTERM */
static volatile int running = 1;
static void handle_sigterm(int sig) { (void)sig; running = 0; }

/**
 * do_read — Đọc file bằng syscall read(), in TEXT + HEX
 * @path: đường dẫn file
 */
static void do_read(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|Không thể mở file: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    /* Đọc toàn bộ file */
    struct stat st;
    if (fstat(fd, &st) == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        close(fd);
        return;
    }

    /* Giới hạn đọc 1MB để tránh tràn bộ nhớ */
    size_t max_read = 1024 * 1024;
    size_t file_size = (size_t)st.st_size;
    if (file_size > max_read) file_size = max_read;

    char *buf = malloc(file_size + 1);
    if (!buf) {
        printf("ERROR|Không đủ bộ nhớ\n");
        close(fd);
        fflush(stdout);
        return;
    }

    ssize_t total = 0;
    while ((size_t)total < file_size) {
        ssize_t n = read(fd, buf + total, file_size - (size_t)total);
        if (n <= 0) break;
        total += n;
    }
    buf[total] = '\0';
    close(fd);

    /* In phần TEXT */
    printf("TEXT_START\n");
    fwrite(buf, 1, (size_t)total, stdout);
    printf("\nTEXT_END\n");

    /* In phần HEX dump */
    printf("HEX_START\n");
    for (ssize_t i = 0; i < total; i += HEX_BYTES_PER_LINE) {
        /* Offset */
        printf("%08x  ", (unsigned int)i);
        /* Hex bytes */
        for (int j = 0; j < HEX_BYTES_PER_LINE; j++) {
            if (i + j < total) printf("%02x ", (unsigned char)buf[i + j]);
            else printf("   ");
            if (j == 7) printf(" ");
        }
        printf(" |");
        /* ASCII */
        for (int j = 0; j < HEX_BYTES_PER_LINE && i + j < total; j++) {
            unsigned char c = (unsigned char)buf[i + j];
            printf("%c", isprint(c) ? c : '.');
        }
        printf("|\n");
    }
    printf("HEX_END\n");

    free(buf);
    fflush(stdout);
}

/**
 * do_write — Ghi file bằng syscall write()
 * @path: đường dẫn file
 * @content: nội dung cần ghi
 */
static void do_write(const char *path, const char *content) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|Không thể mở file để ghi: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    size_t len = strlen(content);
    size_t written = 0;
    while (written < len) {
        ssize_t n = write(fd, content + written, len - written);
        if (n == -1) {
            fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
            printf("ERROR|write() thất bại: %s\n", strerror(errno));
            close(fd);
            fflush(stdout);
            return;
        }
        written += (size_t)n;
    }
    close(fd);
    printf("WRITTEN|%zu\n", written);
    fflush(stdout);
}

/**
 * do_info — Hiển thị metadata file bằng stat()
 * Output: INFO|size|permissions_octal|mtime|uid|gid|owner_name|group_name
 */
static void do_info(const char *path) {
    struct stat st;
    if (stat(path, &st) == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|stat() thất bại: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    /* Lấy tên owner và group */
    struct passwd *pw = getpwuid(st.st_uid);
    struct group *gr = getgrgid(st.st_gid);
    const char *owner_name = pw ? pw->pw_name : "unknown";
    const char *group_name = gr ? gr->gr_name : "unknown";

    printf("INFO|%ld|%04o|%ld|%d|%d|%s|%s\n",
           (long)st.st_size,
           (unsigned int)(st.st_mode & 07777),
           (long)st.st_mtime,
           (int)st.st_uid,
           (int)st.st_gid,
           owner_name,
           group_name);
    fflush(stdout);
}

/**
 * do_append — Ghi thêm vào file bằng syscall write() với O_APPEND
 * @path: đường dẫn file
 * @content: nội dung cần ghi thêm
 */
static void do_append(const char *path, const char *content) {
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|Không thể mở file để append: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    size_t len = strlen(content);
    size_t written = 0;
    while (written < len) {
        ssize_t n = write(fd, content + written, len - written);
        if (n == -1) {
            fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
            printf("ERROR|write() thất bại: %s\n", strerror(errno));
            close(fd);
            fflush(stdout);
            return;
        }
        written += (size_t)n;
    }
    close(fd);
    printf("WRITTEN|%zu\n", written);
    fflush(stdout);
}

/**
 * do_chmod — Thay đổi quyền file
 * @path: đường dẫn file
 * @mode_str: quyền dạng octal string (e.g. "0755")
 */
static void do_chmod(const char *path, const char *mode_str) {
    unsigned int mode;
    if (sscanf(mode_str, "%o", &mode) != 1) {
        printf("ERROR|Mode không hợp lệ: %s\n", mode_str);
        fflush(stdout);
        return;
    }
    if (chmod(path, (mode_t)mode) == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|chmod() thất bại: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }
    printf("OK|chmod|%s|%04o\n", path, mode);
    fflush(stdout);
}

/**
 * do_chown — Thay đổi sở hữu file
 * @path: đường dẫn file
 * @uid: User ID mới
 * @gid: Group ID mới
 */
static void do_chown(const char *path, int uid, int gid) {
    if (chown(path, (uid_t)uid, (gid_t)gid) == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|chown() thất bại: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }
    printf("OK|chown|%s|%d|%d\n", path, uid, gid);
    fflush(stdout);
}

/**
 * do_watch — inotify real-time monitoring
 * Chạy loop liên tục, mỗi event in ra stdout
 * Format: [YYYY-MM-DD HH:MM:SS] EVENT_TYPE path
 * Thoát khi nhận SIGTERM
 */
static void do_watch(const char *path) {
    /* Thiết lập signal handler */
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = handle_sigterm;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);

    int ifd = inotify_init();
    if (ifd < 0) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|inotify_init() thất bại: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    int wd = inotify_add_watch(ifd, path,
        IN_MODIFY | IN_CREATE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO);
    if (wd < 0) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|inotify_add_watch() thất bại: %s\n", strerror(errno));
        close(ifd);
        fflush(stdout);
        return;
    }

    printf("WATCHING|%s\n", path);
    fflush(stdout);

    char buffer[EVENT_BUF_LEN];
    while (running) {
        ssize_t length = read(ifd, buffer, EVENT_BUF_LEN);
        if (length < 0) {
            if (errno == EINTR) continue;
            break;
        }

        ssize_t i = 0;
        while (i < length) {
            struct inotify_event *event = (struct inotify_event *)&buffer[i];

            /* Xác định loại event */
            const char *type = "UNKNOWN";
            if (event->mask & IN_CREATE)      type = "CREATE";
            else if (event->mask & IN_DELETE)  type = "DELETE";
            else if (event->mask & IN_MODIFY)  type = "MODIFY";
            else if (event->mask & IN_MOVED_FROM) type = "MOVED_FROM";
            else if (event->mask & IN_MOVED_TO)   type = "MOVED_TO";

            /* Timestamp */
            time_t now = time(NULL);
            struct tm *tm_info = localtime(&now);
            char ts[32];
            strftime(ts, sizeof(ts), "%Y-%m-%d %H:%M:%S", tm_info);

            /* In event */
            if (event->len > 0) {
                printf("[%s] %s %s/%s\n", ts, type, path, event->name);
            } else {
                printf("[%s] %s %s\n", ts, type, path);
            }
            fflush(stdout);

            i += (ssize_t)(EVENT_SIZE + event->len);
        }
    }

    inotify_rm_watch(ifd, wd);
    close(ifd);
}

/**
 * do_mmap — So sánh hiệu năng mmap vs read
 * Output: MMAP|mmap_usec|read_usec
 */
static void do_mmap(const char *path) {
    struct stat st;
    if (stat(path, &st) == -1) {
        printf("ERROR|stat() thất bại: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    size_t fsize = (size_t)st.st_size;
    if (fsize == 0) {
        printf("ERROR|File rỗng, không thể so sánh\n");
        fflush(stdout);
        return;
    }

    struct timespec t1, t2, t3, t4;
    volatile char sink;

    /* === Test mmap === */
    int fd = open(path, O_RDONLY);
    if (fd == -1) { printf("ERROR|open: %s\n", strerror(errno)); fflush(stdout); return; }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    char *mapped = mmap(NULL, fsize, PROT_READ, MAP_PRIVATE, fd, 0);
    if (mapped == MAP_FAILED) {
        printf("ERROR|mmap: %s\n", strerror(errno));
        close(fd);
        fflush(stdout);
        return;
    }
    /* Đọc qua toàn bộ để buộc page fault */
    for (size_t i = 0; i < fsize; i += 4096) sink = mapped[i];
    (void)sink;
    clock_gettime(CLOCK_MONOTONIC, &t2);
    munmap(mapped, fsize);
    close(fd);

    /* === Test read === */
    fd = open(path, O_RDONLY);
    if (fd == -1) { printf("ERROR|open: %s\n", strerror(errno)); fflush(stdout); return; }

    char rbuf[BUF_SIZE];
    clock_gettime(CLOCK_MONOTONIC, &t3);
    while (read(fd, rbuf, sizeof(rbuf)) > 0);
    clock_gettime(CLOCK_MONOTONIC, &t4);
    close(fd);

    long mmap_us = (t2.tv_sec - t1.tv_sec) * 1000000L + (t2.tv_nsec - t1.tv_nsec) / 1000;
    long read_us = (t4.tv_sec - t3.tv_sec) * 1000000L + (t4.tv_nsec - t3.tv_nsec) / 1000;

    printf("MMAP|%ld|%ld\n", mmap_us, read_us);
    fflush(stdout);
}

int main(int argc, char *argv[]) {
    if (argc < 3) {
        fprintf(stderr, "Sử dụng: %s [read|write|append|info|watch|mmap|chmod|chown] <path> [args]\n", argv[0]);
        return 1;
    }
    const char *cmd = argv[1];
    const char *path = argv[2];

    if (strcmp(cmd, "read") == 0)       do_read(path);
    else if (strcmp(cmd, "write") == 0) {
        if (argc < 4) { printf("ERROR|Thiếu nội dung cần ghi\n"); return 1; }
        /* Ghép tất cả args từ argv[3] trở đi thành content */
        char content[BUF_SIZE * 4] = "";
        for (int i = 3; i < argc; i++) {
            if (i > 3) strcat(content, " ");
            strncat(content, argv[i], sizeof(content) - strlen(content) - 1);
        }
        do_write(path, content);
    }
    else if (strcmp(cmd, "append") == 0) {
        if (argc < 4) { printf("ERROR|Thiếu nội dung cần ghi thêm\n"); return 1; }
        char content[BUF_SIZE * 4] = "";
        for (int i = 3; i < argc; i++) {
            if (i > 3) strcat(content, " ");
            strncat(content, argv[i], sizeof(content) - strlen(content) - 1);
        }
        do_append(path, content);
    }
    else if (strcmp(cmd, "info") == 0)  do_info(path);
    else if (strcmp(cmd, "watch") == 0) do_watch(path);
    else if (strcmp(cmd, "mmap") == 0)  do_mmap(path);
    else if (strcmp(cmd, "chmod") == 0) {
        if (argc < 4) { printf("ERROR|Thiếu mode (e.g. 0755)\n"); return 1; }
        do_chmod(path, argv[3]);
    }
    else if (strcmp(cmd, "chown") == 0) {
        if (argc < 5) { printf("ERROR|Thiếu uid và gid\n"); return 1; }
        do_chown(path, atoi(argv[3]), atoi(argv[4]));
    }
    else { fprintf(stderr, "Lệnh không hợp lệ: %s\n", cmd); return 1; }

    return 0;
}

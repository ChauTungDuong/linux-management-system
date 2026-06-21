/* Bật POSIX extensions (kill, sigaction, ...) — cần trước mọi #include */
#define _POSIX_C_SOURCE 200809L

/*
 * process_mgr.c — Quản lý tiến trình Linux
 * 
 * Chức năng:
 *   - list    : Liệt kê tất cả tiến trình (đọc /proc)
 *   - create  : Tạo tiến trình con bằng fork() + execvp()
 *   - signal  : Gửi signal tới tiến trình
 *   - tree    : Hiển thị cây tiến trình (PID|PPID|NAME)
 *
 * Sử dụng:
 *   ./process_mgr list
 *   ./process_mgr create <cmd> [args...]
 *   ./process_mgr signal <pid> <signal_number>
 *   ./process_mgr tree
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <dirent.h>
#include <unistd.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <ctype.h>

#define BUF_SIZE 4096
#define NAME_SIZE 256
#define PATH_SIZE 512
#define PROTECTED_PID 1

/* Kiểm tra chuỗi có phải toàn chữ số */
static int is_numeric(const char *str) {
    if (!str || !*str) return 0;
    while (*str) { if (!isdigit((unsigned char)*str)) return 0; str++; }
    return 1;
}

/* Lấy uptime hệ thống (giây) từ /proc/uptime */
static double get_system_uptime(void) {
    FILE *fp = fopen("/proc/uptime", "r");
    if (!fp) { fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno)); return -1.0; }
    double up = 0.0;
    if (fscanf(fp, "%lf", &up) != 1) up = -1.0;
    fclose(fp);
    return up;
}

/* Lấy page size (KB) */
static long get_page_size_kb(void) {
    long ps = sysconf(_SC_PAGESIZE);
    return (ps > 0 ? ps : 4096) / 1024;
}

/* Lấy clock ticks per second */
static long get_clk_tck(void) {
    long t = sysconf(_SC_CLK_TCK);
    return t > 0 ? t : 100;
}

/**
 * list_processes — Liệt kê tiến trình
 * Output: PID|NAME|CPU%|MEM_KB|STATE|UID
 */
static void list_processes(void) {
    DIR *d = opendir("/proc");
    if (!d) { fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno)); return; }

    double uptime = get_system_uptime();
    long pskb = get_page_size_kb();
    long tck = get_clk_tck();
    struct dirent *e;

    while ((e = readdir(d)) != NULL) {
        if (!is_numeric(e->d_name)) continue;
        int pid = atoi(e->d_name);
        char path[PATH_SIZE], buf[BUF_SIZE], name[NAME_SIZE];
        char state;
        unsigned long utime = 0, stime = 0;
        unsigned long long starttime = 0;

        snprintf(path, sizeof(path), "/proc/%d/stat", pid);
        FILE *fp = fopen(path, "r");
        if (!fp) continue;
        if (!fgets(buf, sizeof(buf), fp)) { fclose(fp); continue; }
        fclose(fp);

        char *ns = strchr(buf, '('), *ne = strrchr(buf, ')');
        if (!ns || !ne || ne <= ns) continue;
        int nl = (int)(ne - ns - 1);
        if (nl >= NAME_SIZE) nl = NAME_SIZE - 1;
        if (nl < 0) nl = 0;
        /* Dùng memcpy thay strncpy để tránh -Wstringop-truncation */
        memcpy(name, ns + 1, (size_t)nl);
        name[nl] = '\0';

        sscanf(ne + 2, "%c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %lu %lu %*d %*d %*d %*d %*d %*d %llu",
               &state, &utime, &stime, &starttime);

        double cpu = 0.0;
        if (uptime > 0 && tck > 0 && starttime > 0) {
            double tt = (double)(utime + stime) / (double)tck;
            double sec = uptime - ((double)starttime / (double)tck);
            if (sec > 0.0) cpu = (tt / sec) * 100.0;
        }

        long mem_kb = 0;
        snprintf(path, sizeof(path), "/proc/%d/statm", pid);
        fp = fopen(path, "r");
        if (fp) { long sz, res; if (fscanf(fp, "%ld %ld", &sz, &res) >= 2) mem_kb = res * pskb; fclose(fp); }

        /* Lấy UID từ /proc/[pid]/status */
        int uid = -1;
        snprintf(path, sizeof(path), "/proc/%d/status", pid);
        fp = fopen(path, "r");
        if (fp) {
            char status_line[BUF_SIZE];
            while (fgets(status_line, sizeof(status_line), fp)) {
                if (strncmp(status_line, "Uid:", 4) == 0) {
                    sscanf(status_line + 4, "%d", &uid);
                    break;
                }
            }
            fclose(fp);
        }

        printf("%d|%s|%.1f|%ld|%c|%d\n", pid, name, cpu, mem_kb, state, uid);
    }
    closedir(d);
    fflush(stdout);
}

/**
 * create_process — fork() + execvp()
 * Output: CREATED|PID hoặc ERROR|message
 */
static void create_process(int argc, char *argv[]) {
    if (argc < 1 || !argv[0]) { printf("ERROR|Thiếu lệnh cần chạy\n"); fflush(stdout); return; }
    pid_t pid = fork();
    if (pid < 0) { printf("ERROR|fork() thất bại: %s\n", strerror(errno)); fflush(stdout); return; }
    if (pid == 0) {
        freopen("/dev/null", "r", stdin);
        freopen("/dev/null", "w", stdout);
        freopen("/dev/null", "w", stderr);
        execvp(argv[0], argv); 
        _exit(127); 
    }
    printf("CREATED|%d\n", pid);
    fflush(stdout);
}

/**
 * send_signal_to_process — Gửi signal tới PID
 * Output: OK|PID|SIGNAME hoặc ERROR|message
 */
static void send_signal_to_process(int pid, int sig) {
    if (pid == PROTECTED_PID) { printf("ERROR|Không được phép gửi signal tới PID %d (init/systemd)\n", PROTECTED_PID); fflush(stdout); return; }
    if (pid <= 0) { printf("ERROR|PID không hợp lệ: %d\n", pid); fflush(stdout); return; }
    if (kill(pid, sig) == -1) {
        printf("ERROR|kill(%d, %d) thất bại: %s\n", pid, sig, strerror(errno));
    } else {
        const char *sn;
        switch (sig) { 
            case SIGHUP: sn="SIGHUP"; break;
            case SIGINT: sn="SIGINT"; break;
            case SIGQUIT: sn="SIGQUIT"; break;
            case SIGKILL: sn="SIGKILL"; break;
            case SIGUSR1: sn="SIGUSR1"; break;
            case SIGUSR2: sn="SIGUSR2"; break;
            case SIGTERM: sn="SIGTERM"; break; 
            case SIGSTOP: sn="SIGSTOP"; break; 
            case SIGCONT: sn="SIGCONT"; break; 
            default: sn="UNKNOWN"; 
        }
        printf("OK|%d|%s\n", pid, sn);
    }
    fflush(stdout);
}

/**
 * get_process_tree — Cây tiến trình
 * Output: PID|PPID|NAME
 */
static void get_process_tree(void) {
    DIR *d = opendir("/proc");
    if (!d) { fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno)); return; }
    struct dirent *e;
    while ((e = readdir(d)) != NULL) {
        if (!is_numeric(e->d_name)) continue;
        int pid = atoi(e->d_name);
        char path[PATH_SIZE], buf[BUF_SIZE], name[NAME_SIZE] = "";
        int ppid = 0;
        snprintf(path, sizeof(path), "/proc/%d/status", pid);
        FILE *fp = fopen(path, "r");
        if (!fp) continue;
        while (fgets(buf, sizeof(buf), fp)) {
            if (strncmp(buf, "Name:", 5) == 0) {
                char *v = buf + 5; while (*v == ' ' || *v == '\t') v++;
                char *nl = strchr(v, '\n'); if (nl) *nl = '\0';
                /* Dùng snprintf với width limit để tránh warning truncation */
                snprintf(name, NAME_SIZE, "%.*s", NAME_SIZE - 1, v);
            } else if (strncmp(buf, "PPid:", 5) == 0) {
                ppid = atoi(buf + 5);
            }
        }
        fclose(fp);
        printf("%d|%d|%s\n", pid, ppid, name);
    }
    closedir(d);
    fflush(stdout);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Sử dụng: %s [list|create|signal|tree]\n", argv[0]); return 1;
    }
    if (strcmp(argv[1], "list") == 0) { list_processes(); }
    else if (strcmp(argv[1], "create") == 0) {
        if (argc < 3) { printf("ERROR|Thiếu lệnh\n"); return 1; }
        create_process(argc - 2, argv + 2);
    }
    else if (strcmp(argv[1], "signal") == 0) {
        if (argc < 4) { printf("ERROR|Thiếu tham số\n"); return 1; }
        send_signal_to_process(atoi(argv[2]), atoi(argv[3]));
    }
    else if (strcmp(argv[1], "tree") == 0) { get_process_tree(); }
    else { fprintf(stderr, "Lệnh không hợp lệ: %s\n", argv[1]); return 1; }
    return 0;
}

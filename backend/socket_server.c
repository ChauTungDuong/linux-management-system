/* Bật POSIX extensions — cần thiết với -std=c11 cho sigaction, pthread, socket */
#define _POSIX_C_SOURCE 200809L

/*
 * socket_server.c — TCP Server cho chat
 * 
 * Sử dụng: ./socket_server <port>
 * - Bind + listen trên 0.0.0.0:PORT
 * - Accept 1 client, giao tiếp song công
 * - Đọc stdin → gửi tới client
 * - Nhận từ client → in ra stdout
 *
 * Protocol stdout:
 *   STATUS|LISTENING
 *   STATUS|CONNECTED|<client_ip>
 *   STATUS|DISCONNECTED
 *   RECV|<message>
 *   ERROR|<description>
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <signal.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define BUF_SIZE 4096

static volatile int running = 1;
static int client_fd = -1;

static void handle_signal(int sig) { (void)sig; running = 0; }

/**
 * recv_thread — Thread nhận message từ client
 * @arg: không sử dụng
 */
static void *recv_thread(void *arg) {
    (void)arg;
    char buf[BUF_SIZE];
    while (running && client_fd >= 0) {
        ssize_t n = recv(client_fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) {
            if (running) {
                printf("STATUS|DISCONNECTED\n");
                fflush(stdout);
            }
            running = 0;
            break;
        }
        buf[n] = '\0';
        /* Xóa newline cuối nếu có */
        while (n > 0 && (buf[n-1] == '\n' || buf[n-1] == '\r')) buf[--n] = '\0';
        printf("RECV|%s\n", buf);
        fflush(stdout);
    }
    return NULL;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Sử dụng: %s <port>\n", argv[0]);
        return 1;
    }

    /* Thiết lập signal handler */
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = handle_signal;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    signal(SIGPIPE, SIG_IGN); /* Tránh crash khi client ngắt */

    int port = atoi(argv[1]);
    if (port <= 0 || port > 65535) {
        printf("ERROR|Port không hợp lệ: %s\n", argv[1]);
        fflush(stdout);
        return 1;
    }

    /* Tạo socket */
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        printf("ERROR|socket(): %s\n", strerror(errno));
        fflush(stdout);
        return 1;
    }

    /* SO_REUSEADDR để tránh "Address already in use" */
    int opt = 1;
    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
    }

    /* Bind */
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY; /* 0.0.0.0 — accept từ mọi interface */
    addr.sin_port = htons((uint16_t)port);

    if (bind(server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        printf("ERROR|bind(): %s\n", strerror(errno));
        fflush(stdout);
        close(server_fd);
        return 1;
    }

    /* Listen */
    if (listen(server_fd, 1) < 0) {
        printf("ERROR|listen(): %s\n", strerror(errno));
        fflush(stdout);
        close(server_fd);
        return 1;
    }

    printf("STATUS|LISTENING\n");
    fflush(stdout);

    /* Accept client */
    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);
    client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &client_len);
    if (client_fd < 0) {
        if (errno != EINTR) printf("ERROR|accept(): %s\n", strerror(errno));
        close(server_fd);
        fflush(stdout);
        return 1;
    }

    char client_ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, sizeof(client_ip));
    printf("STATUS|CONNECTED|%s\n", client_ip);
    fflush(stdout);

    /* Khởi động thread nhận message */
    pthread_t tid;
    pthread_create(&tid, NULL, recv_thread, NULL);

    /* Main thread: đọc stdin → gửi tới client */
    char input[BUF_SIZE];
    while (running) {
        if (fgets(input, sizeof(input), stdin) == NULL) break;
        /* Xóa newline */
        size_t len = strlen(input);
        while (len > 0 && (input[len-1] == '\n' || input[len-1] == '\r')) input[--len] = '\0';
        if (len == 0) continue;

        /* Gửi message + newline */
        char msg[BUF_SIZE];
        snprintf(msg, sizeof(msg), "%s\n", input);
        if (send(client_fd, msg, strlen(msg), 0) < 0) {
            printf("ERROR|send(): %s\n", strerror(errno));
            fflush(stdout);
            break;
        }
    }

    /* Cleanup */
    running = 0;
    if (client_fd >= 0) { shutdown(client_fd, SHUT_RDWR); close(client_fd); }
    close(server_fd);
    pthread_join(tid, NULL);

    return 0;
}

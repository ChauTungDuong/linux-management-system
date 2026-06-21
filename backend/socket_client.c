/* Bật POSIX extensions — cần thiết với -std=c11 cho sigaction, pthread, getaddrinfo */
#define _POSIX_C_SOURCE 200809L

/*
 * socket_client.c — TCP Client cho chat
 * 
 * Sử dụng: ./socket_client <host> <port>
 * - Connect tới server tại host:port
 * - Đọc stdin → gửi tới server
 * - Nhận từ server → in ra stdout
 *
 * Protocol stdout:
 *   STATUS|CONNECTED
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
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>

#define BUF_SIZE 4096

static volatile int running = 1;
static int sock_fd = -1;

static void handle_signal(int sig) { (void)sig; running = 0; }

/**
 * recv_thread — Thread nhận message từ server
 */
static void *recv_thread(void *arg) {
    (void)arg;
    char buf[BUF_SIZE];
    while (running && sock_fd >= 0) {
        ssize_t n = recv(sock_fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) {
            if (running) {
                printf("STATUS|DISCONNECTED\n");
                fflush(stdout);
            }
            running = 0;
            break;
        }
        buf[n] = '\0';
        while (n > 0 && (buf[n-1] == '\n' || buf[n-1] == '\r')) buf[--n] = '\0';
        printf("RECV|%s\n", buf);
        fflush(stdout);
    }
    return NULL;
}

int main(int argc, char *argv[]) {
    if (argc < 3) {
        fprintf(stderr, "Sử dụng: %s <host> <port>\n", argv[0]);
        return 1;
    }

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = handle_signal;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    signal(SIGPIPE, SIG_IGN);

    const char *host = argv[1];
    int port = atoi(argv[2]);
    if (port <= 0 || port > 65535) {
        printf("ERROR|Port không hợp lệ: %s\n", argv[2]);
        fflush(stdout);
        return 1;
    }

    /* Phân giải hostname */
    struct addrinfo hints, *res;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    int gai_err = getaddrinfo(host, argv[2], &hints, &res);
    if (gai_err != 0) {
        printf("ERROR|Không thể phân giải host '%s': %s\n", host, gai_strerror(gai_err));
        fflush(stdout);
        return 1;
    }

    /* Tạo socket và kết nối */
    sock_fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock_fd < 0) {
        printf("ERROR|socket(): %s\n", strerror(errno));
        freeaddrinfo(res);
        fflush(stdout);
        return 1;
    }

    if (connect(sock_fd, res->ai_addr, res->ai_addrlen) < 0) {
        printf("ERROR|connect(): %s\n", strerror(errno));
        freeaddrinfo(res);
        close(sock_fd);
        fflush(stdout);
        return 1;
    }
    freeaddrinfo(res);

    printf("STATUS|CONNECTED\n");
    fflush(stdout);

    /* Thread nhận message */
    pthread_t tid;
    pthread_create(&tid, NULL, recv_thread, NULL);

    /* Main: đọc stdin → gửi */
    char input[BUF_SIZE];
    while (running) {
        if (fgets(input, sizeof(input), stdin) == NULL) break;
        size_t len = strlen(input);
        while (len > 0 && (input[len-1] == '\n' || input[len-1] == '\r')) input[--len] = '\0';
        if (len == 0) continue;

        char msg[BUF_SIZE];
        snprintf(msg, sizeof(msg), "%s\n", input);
        if (send(sock_fd, msg, strlen(msg), 0) < 0) {
            printf("ERROR|send(): %s\n", strerror(errno));
            fflush(stdout);
            break;
        }
    }

    running = 0;
    if (sock_fd >= 0) { shutdown(sock_fd, SHUT_RDWR); close(sock_fd); }
    pthread_join(tid, NULL);

    return 0;
}

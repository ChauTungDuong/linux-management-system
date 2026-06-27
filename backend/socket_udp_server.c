/* Bật POSIX extensions */
#define _POSIX_C_SOURCE 200809L

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

#define BUF_SIZE 4096

static volatile int running = 1;
static int server_fd = -1;
static struct sockaddr_in client_addr;
static socklen_t client_len = sizeof(client_addr);
static int has_client = 0;

static void handle_signal(int sig) { (void)sig; running = 0; }

static void *recv_thread(void *arg) {
    (void)arg;
    char buf[BUF_SIZE];
    while (running && server_fd >= 0) {
        struct sockaddr_in sender_addr;
        socklen_t sender_len = sizeof(sender_addr);
        ssize_t n = recvfrom(server_fd, buf, sizeof(buf) - 1, 0, (struct sockaddr *)&sender_addr, &sender_len);
        if (n <= 0) {
            running = 0;
            break;
        }
        buf[n] = '\0';
        while (n > 0 && (buf[n-1] == '\n' || buf[n-1] == '\r')) buf[--n] = '\0';
        
        /* Cập nhật client hiện tại để server reply */
        client_addr = sender_addr;
        client_len = sender_len;
        
        if (!has_client) {
            has_client = 1;
            char client_ip[INET_ADDRSTRLEN];
            inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, sizeof(client_ip));
            printf("STATUS|CONNECTED|%s\n", client_ip);
            fflush(stdout);
        }
        
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

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = handle_signal;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);

    int port = atoi(argv[1]);
    server_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (server_fd < 0) {
        printf("ERROR|socket(): %s\n", strerror(errno));
        fflush(stdout);
        return 1;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons((uint16_t)port);

    if (bind(server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        printf("ERROR|bind(): %s\n", strerror(errno));
        fflush(stdout);
        close(server_fd);
        return 1;
    }

    printf("STATUS|LISTENING\n");
    fflush(stdout);

    pthread_t tid;
    pthread_create(&tid, NULL, recv_thread, NULL);

    char input[BUF_SIZE];
    while (running) {
        if (fgets(input, sizeof(input), stdin) == NULL) break;
        if (!has_client) {
            printf("ERROR|Chưa có client gửi tin nhắn đến, không thể gửi lại!\n");
            fflush(stdout);
            continue;
        }
        size_t len = strlen(input);
        while (len > 0 && (input[len-1] == '\n' || input[len-1] == '\r')) input[--len] = '\0';
        if (len == 0) continue;

        char msg[BUF_SIZE];
        snprintf(msg, sizeof(msg), "%s\n", input);
        if (sendto(server_fd, msg, strlen(msg), 0, (struct sockaddr *)&client_addr, client_len) < 0) {
            printf("ERROR|sendto(): %s\n", strerror(errno));
            fflush(stdout);
        }
    }

    running = 0;
    if (server_fd >= 0) close(server_fd);
    pthread_join(tid, NULL);

    return 0;
}

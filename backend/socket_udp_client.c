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
static int client_fd = -1;

static void handle_signal(int sig) { (void)sig; running = 0; }

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

    const char *host = argv[1];
    int port = atoi(argv[2]);

    client_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (client_fd < 0) {
        printf("ERROR|socket(): %s\n", strerror(errno));
        fflush(stdout);
        return 1;
    }

    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons((uint16_t)port);
    if (inet_pton(AF_INET, host, &server_addr.sin_addr) <= 0) {
        printf("ERROR|Địa chỉ IP không hợp lệ: %s\n", host);
        fflush(stdout);
        close(client_fd);
        return 1;
    }

    if (connect(client_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        printf("ERROR|connect(): %s\n", strerror(errno));
        fflush(stdout);
        close(client_fd);
        return 1;
    }

    printf("STATUS|CONNECTED\n");
    fflush(stdout);

    pthread_t tid;
    pthread_create(&tid, NULL, recv_thread, NULL);

    char input[BUF_SIZE];
    while (running) {
        if (fgets(input, sizeof(input), stdin) == NULL) break;
        size_t len = strlen(input);
        while (len > 0 && (input[len-1] == '\n' || input[len-1] == '\r')) input[--len] = '\0';
        if (len == 0) continue;

        char msg[BUF_SIZE];
        snprintf(msg, sizeof(msg), "%s\n", input);
        if (send(client_fd, msg, strlen(msg), 0) < 0) {
            printf("ERROR|send(): %s\n", strerror(errno));
            fflush(stdout);
            break;
        }
    }

    running = 0;
    if (client_fd >= 0) close(client_fd);
    pthread_join(tid, NULL);

    return 0;
}

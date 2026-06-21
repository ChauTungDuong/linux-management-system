/* Bật POSIX extensions — cần thiết với -std=c11 cho getifaddrs, ioctl */
#define _POSIX_C_SOURCE 200809L
/* Cần thêm _DEFAULT_SOURCE để dùng getifaddrs trên glibc hiện đại */
#define _DEFAULT_SOURCE

/*
 * network_info.c — Thông tin mạng Linux
 * 
 * Chức năng:
 *   - interfaces : Liệt kê network interfaces (getifaddrs)
 *   - traffic    : Thống kê traffic (đọc /proc/net/dev)
 *   - route      : Routing table (đọc /proc/net/route)
 *
 * Sử dụng:
 *   ./network_info interfaces
 *   ./network_info traffic
 *   ./network_info route
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <net/if.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <ifaddrs.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <netdb.h>

#define BUF_SIZE 4096

/**
 * list_interfaces — Liệt kê network interfaces
 * Output: IFACE|IPv4|IPv6|MAC|MTU|STATUS
 */
static void list_interfaces(void) {
    struct ifaddrs *ifaddr, *ifa;
    if (getifaddrs(&ifaddr) == -1) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|getifaddrs(): %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    /* Cấu trúc lưu thông tin mỗi interface */
    struct iface_info {
        char name[32];
        char ipv4[INET_ADDRSTRLEN];
        char ipv6[INET6_ADDRSTRLEN];
        char mac[18];
        int mtu;
        int up;
    };

    #define MAX_IFACES 64
    struct iface_info ifaces[MAX_IFACES];
    int count = 0;

    /* Duyệt qua tất cả addresses */
    for (ifa = ifaddr; ifa != NULL; ifa = ifa->ifa_next) {
        if (ifa->ifa_addr == NULL) continue;

        /* Tìm hoặc tạo entry cho interface */
        int idx = -1;
        for (int i = 0; i < count; i++) {
            if (strcmp(ifaces[i].name, ifa->ifa_name) == 0) { idx = i; break; }
        }
        if (idx == -1) {
            if (count >= MAX_IFACES) continue;
            idx = count++;
            memset(&ifaces[idx], 0, sizeof(struct iface_info));
            strncpy(ifaces[idx].name, ifa->ifa_name, sizeof(ifaces[idx].name) - 1);
            ifaces[idx].up = (ifa->ifa_flags & IFF_UP) ? 1 : 0;
        }

        /* IPv4 */
        if (ifa->ifa_addr->sa_family == AF_INET) {
            struct sockaddr_in *sa = (struct sockaddr_in *)ifa->ifa_addr;
            inet_ntop(AF_INET, &sa->sin_addr, ifaces[idx].ipv4, sizeof(ifaces[idx].ipv4));
        }
        /* IPv6 */
        else if (ifa->ifa_addr->sa_family == AF_INET6) {
            struct sockaddr_in6 *sa6 = (struct sockaddr_in6 *)ifa->ifa_addr;
            inet_ntop(AF_INET6, &sa6->sin6_addr, ifaces[idx].ipv6, sizeof(ifaces[idx].ipv6));
        }
        /* MAC (AF_PACKET) */
        else if (ifa->ifa_addr->sa_family == AF_PACKET) {
            struct sockaddr_ll *sll = (struct sockaddr_ll *)ifa->ifa_addr;
            snprintf(ifaces[idx].mac, sizeof(ifaces[idx].mac),
                     "%02X:%02X:%02X:%02X:%02X:%02X",
                     sll->sll_addr[0], sll->sll_addr[1], sll->sll_addr[2],
                     sll->sll_addr[3], sll->sll_addr[4], sll->sll_addr[5]);
        }
    }

    /* Lấy MTU cho mỗi interface */
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd >= 0) {
        for (int i = 0; i < count; i++) {
            struct ifreq ifr;
            memset(&ifr, 0, sizeof(ifr));
            snprintf(ifr.ifr_name, IFNAMSIZ, "%.*s", IFNAMSIZ - 1, ifaces[i].name);
            if (ioctl(sockfd, SIOCGIFMTU, &ifr) == 0) {
                ifaces[i].mtu = ifr.ifr_mtu;
            }
        }
        close(sockfd);
    }

    /* Output */
    for (int i = 0; i < count; i++) {
        printf("%s|%s|%s|%s|%d|%s\n",
               ifaces[i].name,
               ifaces[i].ipv4[0] ? ifaces[i].ipv4 : "",
               ifaces[i].ipv6[0] ? ifaces[i].ipv6 : "",
               ifaces[i].mac[0] ? ifaces[i].mac : "",
               ifaces[i].mtu,
               ifaces[i].up ? "UP" : "DOWN");
    }
    fflush(stdout);
    freeifaddrs(ifaddr);
}

/**
 * get_traffic_stats — Đọc /proc/net/dev
 * Output: IFACE|RX_BYTES|TX_BYTES
 */
static void get_traffic_stats(void) {
    FILE *fp = fopen("/proc/net/dev", "r");
    if (!fp) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|Không thể đọc /proc/net/dev: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    char line[BUF_SIZE];
    /* Bỏ qua 2 dòng header */
    if (fgets(line, sizeof(line), fp) == NULL) { fclose(fp); return; }
    if (fgets(line, sizeof(line), fp) == NULL) { fclose(fp); return; }

    while (fgets(line, sizeof(line), fp) != NULL) {
        char iface[32];
        unsigned long long rx_bytes, tx_bytes;
        /* Format: "  iface: rx_bytes rx_packets ... tx_bytes ..." */
        char *colon = strchr(line, ':');
        if (!colon) continue;

        /* Lấy tên interface */
        *colon = '\0';
        char *name = line;
        while (*name == ' ') name++;
        strncpy(iface, name, sizeof(iface) - 1);
        iface[sizeof(iface) - 1] = '\0';

        /* Parse rx_bytes (field 1) và tx_bytes (field 9) */
        int scanned = sscanf(colon + 1,
            "%llu %*u %*u %*u %*u %*u %*u %*u %llu",
            &rx_bytes, &tx_bytes);
        if (scanned == 2) {
            printf("%s|%llu|%llu\n", iface, rx_bytes, tx_bytes);
        }
    }
    fclose(fp);
    fflush(stdout);
}

/**
 * get_routing_table — Đọc /proc/net/route
 * Output: DEST|GATEWAY|MASK|IFACE|FLAGS
 */
static void get_routing_table(void) {
    FILE *fp = fopen("/proc/net/route", "r");
    if (!fp) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|Không thể đọc /proc/net/route: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    char line[BUF_SIZE];
    /* Bỏ qua header */
    if (fgets(line, sizeof(line), fp) == NULL) { fclose(fp); return; }

    while (fgets(line, sizeof(line), fp) != NULL) {
        char iface[32];
        unsigned int dest, gateway, mask, flags;
        int scanned = sscanf(line, "%31s %X %X %u %*d %*d %*d %X",
                             iface, &dest, &gateway, &flags, &mask);
        if (scanned < 5) continue;

        /* Chuyển hex thành IP dạng dotted decimal */
        struct in_addr d, g, m;
        d.s_addr = dest;
        g.s_addr = gateway;
        m.s_addr = mask;

        char dest_str[INET_ADDRSTRLEN], gw_str[INET_ADDRSTRLEN], mask_str[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &d, dest_str, sizeof(dest_str));
        inet_ntop(AF_INET, &g, gw_str, sizeof(gw_str));
        inet_ntop(AF_INET, &m, mask_str, sizeof(mask_str));

        /* Decode flags */
        char flag_str[16] = "";
        if (flags & 0x0001) strcat(flag_str, "U");
        if (flags & 0x0002) strcat(flag_str, "G");
        if (flags & 0x0004) strcat(flag_str, "H");

        printf("%s|%s|%s|%s|%s\n", dest_str, gw_str, mask_str, iface, flag_str);
    }
    fclose(fp);
    fflush(stdout);
}

/**
 * do_dns_lookup — Phân giải hostname bằng getaddrinfo()
 * Output: DNS|hostname|ip_address (mỗi IP 1 dòng)
 */
static void do_dns_lookup(const char *hostname) {
    struct addrinfo hints, *res, *p;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;     /* IPv4 + IPv6 */
    hints.ai_socktype = SOCK_STREAM;

    int status = getaddrinfo(hostname, NULL, &hints, &res);
    if (status != 0) {
        printf("ERROR|Không thể phân giải '%s': %s\n", hostname, gai_strerror(status));
        fflush(stdout);
        return;
    }

    for (p = res; p != NULL; p = p->ai_next) {
        char ipstr[INET6_ADDRSTRLEN];
        void *addr;
        const char *ipver;

        if (p->ai_family == AF_INET) {
            struct sockaddr_in *ipv4 = (struct sockaddr_in *)p->ai_addr;
            addr = &(ipv4->sin_addr);
            ipver = "IPv4";
        } else {
            struct sockaddr_in6 *ipv6 = (struct sockaddr_in6 *)p->ai_addr;
            addr = &(ipv6->sin6_addr);
            ipver = "IPv6";
        }

        inet_ntop(p->ai_family, addr, ipstr, sizeof(ipstr));
        printf("DNS|%s|%s|%s\n", hostname, ipver, ipstr);
    }

    freeaddrinfo(res);
    fflush(stdout);
}

/**
 * get_arp_table — Đọc /proc/net/arp
 * Output: IP|HW_TYPE|FLAGS|MAC|MASK|DEVICE
 */
static void get_arp_table(void) {
    FILE *fp = fopen("/proc/net/arp", "r");
    if (!fp) {
        fprintf(stderr, "Lỗi tại %s:%d — %s\n", __FILE__, __LINE__, strerror(errno));
        printf("ERROR|Không thể đọc /proc/net/arp: %s\n", strerror(errno));
        fflush(stdout);
        return;
    }

    char line[BUF_SIZE];
    /* Bỏ qua header */
    if (fgets(line, sizeof(line), fp) == NULL) { fclose(fp); return; }

    while (fgets(line, sizeof(line), fp) != NULL) {
        char ip[64], hw_type[16], flags[16], mac[32], mask[16], device[32];
        int scanned = sscanf(line, "%63s %15s %15s %31s %15s %31s",
                             ip, hw_type, flags, mac, mask, device);
        if (scanned >= 6) {
            printf("%s|%s|%s|%s|%s|%s\n", ip, hw_type, flags, mac, mask, device);
        }
    }
    fclose(fp);
    fflush(stdout);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Sử dụng: %s [interfaces|traffic|route|dns|arp] [args]\n", argv[0]);
        return 1;
    }

    if (strcmp(argv[1], "interfaces") == 0)      list_interfaces();
    else if (strcmp(argv[1], "traffic") == 0)     get_traffic_stats();
    else if (strcmp(argv[1], "route") == 0)       get_routing_table();
    else if (strcmp(argv[1], "dns") == 0) {
        if (argc < 3) { printf("ERROR|Thiếu hostname\n"); fflush(stdout); return 1; }
        do_dns_lookup(argv[2]);
    }
    else if (strcmp(argv[1], "arp") == 0)         get_arp_table();
    else { fprintf(stderr, "Lệnh không hợp lệ: %s\n", argv[1]); return 1; }

    return 0;
}

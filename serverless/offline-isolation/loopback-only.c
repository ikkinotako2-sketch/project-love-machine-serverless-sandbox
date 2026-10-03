#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <errno.h>
static int safe(const struct sockaddr *a){if(!a)return 0;if(a->sa_family==AF_UNIX)return 1;if(a->sa_family==AF_INET)return (ntohl(((const struct sockaddr_in*)a)->sin_addr.s_addr)>>24)==127;if(a->sa_family==AF_INET6)return IN6_IS_ADDR_LOOPBACK(&((const struct sockaddr_in6*)a)->sin6_addr);return 0;}
int connect(int f,const struct sockaddr*a,socklen_t n){if(!safe(a)){errno=EPERM;return -1;}int(*fn)(int,const struct sockaddr*,socklen_t)=dlsym(RTLD_NEXT,"connect");return fn(f,a,n);}
int bind(int f,const struct sockaddr*a,socklen_t n){if(!safe(a)){errno=EPERM;return -1;}int(*fn)(int,const struct sockaddr*,socklen_t)=dlsym(RTLD_NEXT,"bind");return fn(f,a,n);}
ssize_t sendto(int f,const void*b,size_t n,int flags,const struct sockaddr*a,socklen_t l){if(a&&!safe(a)){errno=EPERM;return -1;}ssize_t(*fn)(int,const void*,size_t,int,const struct sockaddr*,socklen_t)=dlsym(RTLD_NEXT,"sendto");return fn(f,b,n,flags,a,l);}

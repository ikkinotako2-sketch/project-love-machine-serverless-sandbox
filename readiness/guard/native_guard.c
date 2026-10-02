/* Linux test-process guard. No secret access, networking or external clients. */
#define _GNU_SOURCE
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>

#if defined(__x86_64__)
#define EXPECTED_ARCH AUDIT_ARCH_X86_64
#elif defined(__aarch64__)
#define EXPECTED_ARCH AUDIT_ARCH_AARCH64
#else
#error Unsupported architecture: fail closed
#endif
#define DENY(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, (n), 0, 1), BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|EPERM)

__attribute__((constructor)) static void guard_install(void) {
    const char *names[] = {"TEST_ONLY", "DRY_RUN", "NO_PUBLISH", "EMERGENCY_STOP"};
    for (unsigned i=0;i<4;i++) {
        const char *value=getenv(names[i]);
        if (!value || strcmp(value,"true")) _exit(90);
    }
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data,arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,EXPECTED_ARCH,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data,nr)),
#if defined(__x86_64__)
        BPF_JUMP(BPF_JMP|BPF_JGE|BPF_K,0x40000000,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
#endif
        DENY(SYS_execve), DENY(SYS_execveat),
        DENY(SYS_socket), DENY(SYS_socketpair), DENY(SYS_connect),
        DENY(SYS_sendto), DENY(SYS_sendmsg), DENY(SYS_sendmmsg),
        DENY(SYS_ptrace), DENY(SYS_process_vm_writev),
        DENY(SYS_io_uring_setup), DENY(SYS_bpf),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program={sizeof(filter)/sizeof(filter[0]),filter};
    if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0) ||
       syscall(SYS_seccomp,SECCOMP_SET_MODE_FILTER,SECCOMP_FILTER_FLAG_TSYNC,&program)) _exit(91);
}
int plm_guard_active(void) { return prctl(PR_GET_SECCOMP,0,0,0,0)==SECCOMP_MODE_FILTER; }

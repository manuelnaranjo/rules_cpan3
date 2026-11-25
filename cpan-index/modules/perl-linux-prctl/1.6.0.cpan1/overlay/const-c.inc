#define PERL_constant_NOTFOUND	1
#define PERL_constant_NOTDEF	2
#define PERL_constant_ISIV	3
#define PERL_constant_ISNO	4
#define PERL_constant_ISNV	5
#define PERL_constant_ISPV	6
#define PERL_constant_ISPVN	7
#define PERL_constant_ISSV	8
#define PERL_constant_ISUNDEF	9
#define PERL_constant_ISUV	10
#define PERL_constant_ISYES	11

#ifndef NVTYPE
typedef double NV; /* 5.6 and later define NVTYPE, and typedef NV to it.  */
#endif
#ifndef aTHX_
#define aTHX_ /* 5.6 or later define this for threading support.  */
#endif
#ifndef pTHX_
#define pTHX_ /* 5.6 or later define this for threading support.  */
#endif

static int
constant_9 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_CHOWN CAP_LEASE CAP_MKNOD */
  /* Offset 5 gives the best switch position.  */
  switch (name[5]) {
  case 'E':
    if (memEQ(name, "CAP_LEASE", 9)) {
    /*                    ^         */
#ifdef CAP_LEASE
      *iv_return = CAP_LEASE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'H':
    if (memEQ(name, "CAP_CHOWN", 9)) {
    /*                    ^         */
#ifdef CAP_CHOWN
      *iv_return = CAP_CHOWN;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'K':
    if (memEQ(name, "CAP_MKNOD", 9)) {
    /*                    ^         */
#ifdef CAP_MKNOD
      *iv_return = CAP_MKNOD;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_10 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_FOWNER CAP_FSETID CAP_SETGID CAP_SETUID CAP_SYSLOG ENDIAN_BIG
     FP_EXC_DIV FP_EXC_INV FP_EXC_OVF FP_EXC_RES FP_EXC_UND TSC_ENABLE */
  /* Offset 7 gives the best switch position.  */
  switch (name[7]) {
  case 'B':
    if (memEQ(name, "ENDIAN_BIG", 10)) {
    /*                      ^         */
#ifdef PR_ENDIAN_BIG
      *iv_return = PR_ENDIAN_BIG;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    if (memEQ(name, "TSC_ENABLE", 10)) {
    /*                      ^         */
#ifdef PR_TSC_ENABLE
      *iv_return = PR_TSC_ENABLE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'D':
    if (memEQ(name, "FP_EXC_DIV", 10)) {
    /*                      ^         */
#ifdef PR_FP_EXC_DIV
      *iv_return = PR_FP_EXC_DIV;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'G':
    if (memEQ(name, "CAP_SETGID", 10)) {
    /*                      ^         */
#ifdef CAP_SETGID
      *iv_return = CAP_SETGID;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'I':
    if (memEQ(name, "FP_EXC_INV", 10)) {
    /*                      ^         */
#ifdef PR_FP_EXC_INV
      *iv_return = PR_FP_EXC_INV;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'L':
    if (memEQ(name, "CAP_SYSLOG", 10)) {
    /*                      ^         */
#ifdef CAP_SYSLOG
      *iv_return = CAP_SYSLOG;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'N':
    if (memEQ(name, "CAP_FOWNER", 10)) {
    /*                      ^         */
#ifdef CAP_FOWNER
      *iv_return = CAP_FOWNER;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'O':
    if (memEQ(name, "FP_EXC_OVF", 10)) {
    /*                      ^         */
#ifdef PR_FP_EXC_OVF
      *iv_return = PR_FP_EXC_OVF;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'R':
    if (memEQ(name, "FP_EXC_RES", 10)) {
    /*                      ^         */
#ifdef PR_FP_EXC_RES
      *iv_return = PR_FP_EXC_RES;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'T':
    if (memEQ(name, "CAP_FSETID", 10)) {
    /*                      ^         */
#ifdef CAP_FSETID
      *iv_return = CAP_FSETID;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'U':
    if (memEQ(name, "CAP_SETUID", 10)) {
    /*                      ^         */
#ifdef CAP_SETUID
      *iv_return = CAP_SETUID;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    if (memEQ(name, "FP_EXC_UND", 10)) {
    /*                      ^         */
#ifdef PR_FP_EXC_UND
      *iv_return = PR_FP_EXC_UND;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_11 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_NET_RAW CAP_SETFCAP CAP_SETPCAP TSC_SIGSEGV */
  /* Offset 7 gives the best switch position.  */
  switch (name[7]) {
  case 'F':
    if (memEQ(name, "CAP_SETFCAP", 11)) {
    /*                      ^          */
#ifdef CAP_SETFCAP
      *iv_return = CAP_SETFCAP;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'P':
    if (memEQ(name, "CAP_SETPCAP", 11)) {
    /*                      ^          */
#ifdef CAP_SETPCAP
      *iv_return = CAP_SETPCAP;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'S':
    if (memEQ(name, "TSC_SIGSEGV", 11)) {
    /*                      ^          */
#ifdef PR_TSC_SIGSEGV
      *iv_return = PR_TSC_SIGSEGV;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case '_':
    if (memEQ(name, "CAP_NET_RAW", 11)) {
    /*                      ^          */
#ifdef CAP_NET_RAW
      *iv_return = CAP_NET_RAW;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_12 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_IPC_LOCK CAP_SYS_BOOT CAP_SYS_NICE CAP_SYS_TIME FPEMU_SIGFPE
     FP_EXC_ASYNC */
  /* Offset 8 gives the best switch position.  */
  switch (name[8]) {
  case 'B':
    if (memEQ(name, "CAP_SYS_BOOT", 12)) {
    /*                       ^          */
#ifdef CAP_SYS_BOOT
      *iv_return = CAP_SYS_BOOT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'G':
    if (memEQ(name, "FPEMU_SIGFPE", 12)) {
    /*                       ^          */
#ifdef PR_FPEMU_SIGFPE
      *iv_return = PR_FPEMU_SIGFPE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'L':
    if (memEQ(name, "CAP_IPC_LOCK", 12)) {
    /*                       ^          */
#ifdef CAP_IPC_LOCK
      *iv_return = CAP_IPC_LOCK;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'N':
    if (memEQ(name, "CAP_SYS_NICE", 12)) {
    /*                       ^          */
#ifdef CAP_SYS_NICE
      *iv_return = CAP_SYS_NICE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'S':
    if (memEQ(name, "FP_EXC_ASYNC", 12)) {
    /*                       ^          */
#ifdef PR_FP_EXC_ASYNC
      *iv_return = PR_FP_EXC_ASYNC;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'T':
    if (memEQ(name, "CAP_SYS_TIME", 12)) {
    /*                       ^          */
#ifdef CAP_SYS_TIME
      *iv_return = CAP_SYS_TIME;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_13 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_EFFECTIVE CAP_IPC_OWNER CAP_MAC_ADMIN CAP_NET_ADMIN CAP_PERMITTED
     CAP_SYS_ADMIN CAP_SYS_PACCT CAP_SYS_RAWIO ENDIAN_LITTLE FPEMU_NOPRINT
     MCE_KILL_LATE SECBIT_NOROOT SECURE_NOROOT */
  /* Offset 4 gives the best switch position.  */
  switch (name[4]) {
  case 'A':
    if (memEQ(name, "ENDIAN_LITTLE", 13)) {
    /*                   ^               */
#ifdef PR_ENDIAN_LITTLE
      *iv_return = PR_ENDIAN_LITTLE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'E':
    if (memEQ(name, "CAP_EFFECTIVE", 13)) {
    /*                   ^               */
#ifdef CAP_EFFECTIVE
      *iv_return = CAP_EFFECTIVE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'I':
    if (memEQ(name, "CAP_IPC_OWNER", 13)) {
    /*                   ^               */
#ifdef CAP_IPC_OWNER
      *iv_return = CAP_IPC_OWNER;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    if (memEQ(name, "SECBIT_NOROOT", 13)) {
    /*                   ^               */
#ifdef SECBIT_NOROOT
      *iv_return = SECBIT_NOROOT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'K':
    if (memEQ(name, "MCE_KILL_LATE", 13)) {
    /*                   ^               */
#ifdef PR_MCE_KILL_LATE
      *iv_return = PR_MCE_KILL_LATE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'M':
    if (memEQ(name, "CAP_MAC_ADMIN", 13)) {
    /*                   ^               */
#ifdef CAP_MAC_ADMIN
      *iv_return = CAP_MAC_ADMIN;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'N':
    if (memEQ(name, "CAP_NET_ADMIN", 13)) {
    /*                   ^               */
#ifdef CAP_NET_ADMIN
      *iv_return = CAP_NET_ADMIN;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'P':
    if (memEQ(name, "CAP_PERMITTED", 13)) {
    /*                   ^               */
#ifdef CAP_PERMITTED
      *iv_return = CAP_PERMITTED;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'R':
    if (memEQ(name, "SECURE_NOROOT", 13)) {
    /*                   ^               */
#ifdef SECURE_NOROOT
      *iv_return = SECURE_NOROOT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'S':
    if (memEQ(name, "CAP_SYS_ADMIN", 13)) {
    /*                   ^               */
#ifdef CAP_SYS_ADMIN
      *iv_return = CAP_SYS_ADMIN;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    if (memEQ(name, "CAP_SYS_PACCT", 13)) {
    /*                   ^               */
#ifdef CAP_SYS_PACCT
      *iv_return = CAP_SYS_PACCT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    if (memEQ(name, "CAP_SYS_RAWIO", 13)) {
    /*                   ^               */
#ifdef CAP_SYS_RAWIO
      *iv_return = CAP_SYS_RAWIO;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'U':
    if (memEQ(name, "FPEMU_NOPRINT", 13)) {
    /*                   ^               */
#ifdef PR_FPEMU_NOPRINT
      *iv_return = PR_FPEMU_NOPRINT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_14 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_SYS_CHROOT CAP_SYS_MODULE CAP_SYS_PTRACE CAP_WAKE_ALARM FP_EXC_PRECISE
     MCE_KILL_EARLY UNALIGN_SIGBUS */
  /* Offset 10 gives the best switch position.  */
  switch (name[10]) {
  case 'A':
    if (memEQ(name, "MCE_KILL_EARLY", 14)) {
    /*                         ^          */
#ifdef PR_MCE_KILL_EARLY
      *iv_return = PR_MCE_KILL_EARLY;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'C':
    if (memEQ(name, "FP_EXC_PRECISE", 14)) {
    /*                         ^          */
#ifdef PR_FP_EXC_PRECISE
      *iv_return = PR_FP_EXC_PRECISE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'D':
    if (memEQ(name, "CAP_SYS_MODULE", 14)) {
    /*                         ^          */
#ifdef CAP_SYS_MODULE
      *iv_return = CAP_SYS_MODULE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'G':
    if (memEQ(name, "UNALIGN_SIGBUS", 14)) {
    /*                         ^          */
#ifdef PR_UNALIGN_SIGBUS
      *iv_return = PR_UNALIGN_SIGBUS;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'L':
    if (memEQ(name, "CAP_WAKE_ALARM", 14)) {
    /*                         ^          */
#ifdef CAP_WAKE_ALARM
      *iv_return = CAP_WAKE_ALARM;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'R':
    if (memEQ(name, "CAP_SYS_CHROOT", 14)) {
    /*                         ^          */
#ifdef CAP_SYS_CHROOT
      *iv_return = CAP_SYS_CHROOT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    if (memEQ(name, "CAP_SYS_PTRACE", 14)) {
    /*                         ^          */
#ifdef CAP_SYS_PTRACE
      *iv_return = CAP_SYS_PTRACE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_15 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_AUDIT_WRITE CAP_INHERITABLE FP_EXC_DISABLED FP_EXC_NONRECOV
     UNALIGN_NOPRINT */
  /* Offset 8 gives the best switch position.  */
  switch (name[8]) {
  case 'I':
    if (memEQ(name, "FP_EXC_DISABLED", 15)) {
    /*                       ^             */
#ifdef PR_FP_EXC_DISABLED
      *iv_return = PR_FP_EXC_DISABLED;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'N':
    if (memEQ(name, "UNALIGN_NOPRINT", 15)) {
    /*                       ^             */
#ifdef PR_UNALIGN_NOPRINT
      *iv_return = PR_UNALIGN_NOPRINT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'O':
    if (memEQ(name, "FP_EXC_NONRECOV", 15)) {
    /*                       ^             */
#ifdef PR_FP_EXC_NONRECOV
      *iv_return = PR_FP_EXC_NONRECOV;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'R':
    if (memEQ(name, "CAP_INHERITABLE", 15)) {
    /*                       ^             */
#ifdef CAP_INHERITABLE
      *iv_return = CAP_INHERITABLE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'T':
    if (memEQ(name, "CAP_AUDIT_WRITE", 15)) {
    /*                       ^             */
#ifdef CAP_AUDIT_WRITE
      *iv_return = CAP_AUDIT_WRITE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_16 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_DAC_OVERRIDE CAP_MAC_OVERRIDE CAP_SYS_RESOURCE FP_EXC_SW_ENABLE
     MCE_KILL_DEFAULT SECBIT_KEEP_CAPS SECURE_KEEP_CAPS TIMING_TIMESTAMP */
  /* Offset 4 gives the best switch position.  */
  switch (name[4]) {
  case 'D':
    if (memEQ(name, "CAP_DAC_OVERRIDE", 16)) {
    /*                   ^                  */
#ifdef CAP_DAC_OVERRIDE
      *iv_return = CAP_DAC_OVERRIDE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'I':
    if (memEQ(name, "SECBIT_KEEP_CAPS", 16)) {
    /*                   ^                  */
#ifdef SECBIT_KEEP_CAPS
      *iv_return = SECBIT_KEEP_CAPS;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'K':
    if (memEQ(name, "MCE_KILL_DEFAULT", 16)) {
    /*                   ^                  */
#ifdef PR_MCE_KILL_DEFAULT
      *iv_return = PR_MCE_KILL_DEFAULT;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'M':
    if (memEQ(name, "CAP_MAC_OVERRIDE", 16)) {
    /*                   ^                  */
#ifdef CAP_MAC_OVERRIDE
      *iv_return = CAP_MAC_OVERRIDE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'N':
    if (memEQ(name, "TIMING_TIMESTAMP", 16)) {
    /*                   ^                  */
#ifdef PR_TIMING_TIMESTAMP
      *iv_return = PR_TIMING_TIMESTAMP;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'R':
    if (memEQ(name, "SECURE_KEEP_CAPS", 16)) {
    /*                   ^                  */
#ifdef SECURE_KEEP_CAPS
      *iv_return = SECURE_KEEP_CAPS;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'S':
    if (memEQ(name, "CAP_SYS_RESOURCE", 16)) {
    /*                   ^                  */
#ifdef CAP_SYS_RESOURCE
      *iv_return = CAP_SYS_RESOURCE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'X':
    if (memEQ(name, "FP_EXC_SW_ENABLE", 16)) {
    /*                   ^                  */
#ifdef PR_FP_EXC_SW_ENABLE
      *iv_return = PR_FP_EXC_SW_ENABLE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_17 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_AUDIT_CONTROL CAP_NET_BROADCAST ENDIAN_PPC_LITTLE */
  /* Offset 15 gives the best switch position.  */
  switch (name[15]) {
  case 'L':
    if (memEQ(name, "ENDIAN_PPC_LITTLE", 17)) {
    /*                              ^        */
#ifdef PR_ENDIAN_PPC_LITTLE
      *iv_return = PR_ENDIAN_PPC_LITTLE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'O':
    if (memEQ(name, "CAP_AUDIT_CONTROL", 17)) {
    /*                              ^        */
#ifdef CAP_AUDIT_CONTROL
      *iv_return = CAP_AUDIT_CONTROL;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'S':
    if (memEQ(name, "CAP_NET_BROADCAST", 17)) {
    /*                              ^        */
#ifdef CAP_NET_BROADCAST
      *iv_return = CAP_NET_BROADCAST;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant_20 (pTHX_ const char *name, IV *iv_return) {
  /* When generated this function returned values for the list of names given
     here.  However, subsequent manual editing may have added or removed some.
     CAP_NET_BIND_SERVICE SECBIT_NOROOT_LOCKED SECURE_NOROOT_LOCKED */
  /* Offset 4 gives the best switch position.  */
  switch (name[4]) {
  case 'I':
    if (memEQ(name, "SECBIT_NOROOT_LOCKED", 20)) {
    /*                   ^                      */
#ifdef SECBIT_NOROOT_LOCKED
      *iv_return = SECBIT_NOROOT_LOCKED;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'N':
    if (memEQ(name, "CAP_NET_BIND_SERVICE", 20)) {
    /*                   ^                      */
#ifdef CAP_NET_BIND_SERVICE
      *iv_return = CAP_NET_BIND_SERVICE;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 'R':
    if (memEQ(name, "SECURE_NOROOT_LOCKED", 20)) {
    /*                   ^                      */
#ifdef SECURE_NOROOT_LOCKED
      *iv_return = SECURE_NOROOT_LOCKED;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

static int
constant (pTHX_ const char *name, STRLEN len, IV *iv_return) {
  /* Initially switch on the length of the name.  */
  /* When generated this function returned values for the list of names given
     in this section of perl code.  Rather than manually editing these functions
     to add or remove constants, which would result in this comment and section
     of code becoming inaccurate, we recommend that you edit this section of
     code, and use it to regenerate a new set of constant functions which you
     then use to replace the originals.

     Regenerate these constant functions by feeding this entire source file to
     perl -x

#!/usr/bin/perl -w
use ExtUtils::Constant qw (constant_types C_constant XS_constant);

my $types = {map {($_, 1)} qw(IV)};
my @names = (qw(CAP_AUDIT_CONTROL CAP_AUDIT_WRITE CAP_CHOWN CAP_DAC_OVERRIDE
	       CAP_DAC_READ_SEARCH CAP_EFFECTIVE CAP_FOWNER CAP_FSETID
	       CAP_INHERITABLE CAP_IPC_LOCK CAP_IPC_OWNER CAP_KILL CAP_LEASE
	       CAP_LINUX_IMMUTABLE CAP_MAC_ADMIN CAP_MAC_OVERRIDE CAP_MKNOD
	       CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_BROADCAST CAP_NET_RAW
	       CAP_PERMITTED CAP_SETFCAP CAP_SETGID CAP_SETPCAP CAP_SETUID
	       CAP_SYSLOG CAP_SYS_ADMIN CAP_SYS_BOOT CAP_SYS_CHROOT
	       CAP_SYS_MODULE CAP_SYS_NICE CAP_SYS_PACCT CAP_SYS_PTRACE
	       CAP_SYS_RAWIO CAP_SYS_RESOURCE CAP_SYS_TIME CAP_SYS_TTY_CONFIG
	       CAP_WAKE_ALARM ENDIAN_BIG ENDIAN_LITTLE ENDIAN_PPC_LITTLE
	       FPEMU_NOPRINT FPEMU_SIGFPE FP_EXC_ASYNC FP_EXC_DISABLED
	       FP_EXC_DIV FP_EXC_INV FP_EXC_NONRECOV FP_EXC_OVF FP_EXC_PRECISE
	       FP_EXC_RES FP_EXC_SW_ENABLE FP_EXC_UND MCE_KILL_DEFAULT
	       MCE_KILL_EARLY MCE_KILL_LATE SECBIT_KEEP_CAPS
	       SECBIT_KEEP_CAPS_LOCKED SECBIT_NOROOT SECBIT_NOROOT_LOCKED
	       SECBIT_NO_SETUID_FIXUP SECBIT_NO_SETUID_FIXUP_LOCKED
	       SECURE_KEEP_CAPS SECURE_KEEP_CAPS_LOCKED SECURE_NOROOT
	       SECURE_NOROOT_LOCKED SECURE_NO_SETUID_FIXUP
	       SECURE_NO_SETUID_FIXUP_LOCKED TIMING_STATISTICAL
	       TIMING_TIMESTAMP TSC_ENABLE TSC_SIGSEGV UNALIGN_NOPRINT
	       UNALIGN_SIGBUS));

print constant_types(), "\n"; # macro defs
foreach (C_constant ("Linux::Prctl", 'constant', 'IV', $types, undef, 3, @names) ) {
    print $_, "\n"; # C constant subs
}
print "\n#### XS Section:\n";
print XS_constant ("Linux::Prctl", $types);
__END__
   */

  switch (len) {
  case 8:
    if (memEQ(name, "CAP_KILL", 8)) {
#ifdef CAP_KILL
      *iv_return = CAP_KILL;
      return PERL_constant_ISIV;
#else
      return PERL_constant_NOTDEF;
#endif
    }
    break;
  case 9:
    return constant_9 (aTHX_ name, iv_return);
    break;
  case 10:
    return constant_10 (aTHX_ name, iv_return);
    break;
  case 11:
    return constant_11 (aTHX_ name, iv_return);
    break;
  case 12:
    return constant_12 (aTHX_ name, iv_return);
    break;
  case 13:
    return constant_13 (aTHX_ name, iv_return);
    break;
  case 14:
    return constant_14 (aTHX_ name, iv_return);
    break;
  case 15:
    return constant_15 (aTHX_ name, iv_return);
    break;
  case 16:
    return constant_16 (aTHX_ name, iv_return);
    break;
  case 17:
    return constant_17 (aTHX_ name, iv_return);
    break;
  case 18:
    /* Names all of length 18.  */
    /* CAP_SYS_TTY_CONFIG TIMING_STATISTICAL */
    /* Offset 2 gives the best switch position.  */
    switch (name[2]) {
    case 'M':
      if (memEQ(name, "TIMING_STATISTICAL", 18)) {
      /*                 ^                      */
#ifdef PR_TIMING_STATISTICAL
        *iv_return = PR_TIMING_STATISTICAL;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    case 'P':
      if (memEQ(name, "CAP_SYS_TTY_CONFIG", 18)) {
      /*                 ^                      */
#ifdef CAP_SYS_TTY_CONFIG
        *iv_return = CAP_SYS_TTY_CONFIG;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    }
    break;
  case 19:
    /* Names all of length 19.  */
    /* CAP_DAC_READ_SEARCH CAP_LINUX_IMMUTABLE */
    /* Offset 13 gives the best switch position.  */
    switch (name[13]) {
    case 'S':
      if (memEQ(name, "CAP_DAC_READ_SEARCH", 19)) {
      /*                            ^            */
#ifdef CAP_DAC_READ_SEARCH
        *iv_return = CAP_DAC_READ_SEARCH;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    case 'U':
      if (memEQ(name, "CAP_LINUX_IMMUTABLE", 19)) {
      /*                            ^            */
#ifdef CAP_LINUX_IMMUTABLE
        *iv_return = CAP_LINUX_IMMUTABLE;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    }
    break;
  case 20:
    return constant_20 (aTHX_ name, iv_return);
    break;
  case 22:
    /* Names all of length 22.  */
    /* SECBIT_NO_SETUID_FIXUP SECURE_NO_SETUID_FIXUP */
    /* Offset 4 gives the best switch position.  */
    switch (name[4]) {
    case 'I':
      if (memEQ(name, "SECBIT_NO_SETUID_FIXUP", 22)) {
      /*                   ^                        */
#ifdef SECBIT_NO_SETUID_FIXUP
        *iv_return = SECBIT_NO_SETUID_FIXUP;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    case 'R':
      if (memEQ(name, "SECURE_NO_SETUID_FIXUP", 22)) {
      /*                   ^                        */
#ifdef SECURE_NO_SETUID_FIXUP
        *iv_return = SECURE_NO_SETUID_FIXUP;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    }
    break;
  case 23:
    /* Names all of length 23.  */
    /* SECBIT_KEEP_CAPS_LOCKED SECURE_KEEP_CAPS_LOCKED */
    /* Offset 4 gives the best switch position.  */
    switch (name[4]) {
    case 'I':
      if (memEQ(name, "SECBIT_KEEP_CAPS_LOCKED", 23)) {
      /*                   ^                         */
#ifdef SECBIT_KEEP_CAPS_LOCKED
        *iv_return = SECBIT_KEEP_CAPS_LOCKED;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    case 'R':
      if (memEQ(name, "SECURE_KEEP_CAPS_LOCKED", 23)) {
      /*                   ^                         */
#ifdef SECURE_KEEP_CAPS_LOCKED
        *iv_return = SECURE_KEEP_CAPS_LOCKED;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    }
    break;
  case 29:
    /* Names all of length 29.  */
    /* SECBIT_NO_SETUID_FIXUP_LOCKED SECURE_NO_SETUID_FIXUP_LOCKED */
    /* Offset 4 gives the best switch position.  */
    switch (name[4]) {
    case 'I':
      if (memEQ(name, "SECBIT_NO_SETUID_FIXUP_LOCKED", 29)) {
      /*                   ^                               */
#ifdef SECBIT_NO_SETUID_FIXUP_LOCKED
        *iv_return = SECBIT_NO_SETUID_FIXUP_LOCKED;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    case 'R':
      if (memEQ(name, "SECURE_NO_SETUID_FIXUP_LOCKED", 29)) {
      /*                   ^                               */
#ifdef SECURE_NO_SETUID_FIXUP_LOCKED
        *iv_return = SECURE_NO_SETUID_FIXUP_LOCKED;
        return PERL_constant_ISIV;
#else
        return PERL_constant_NOTDEF;
#endif
      }
      break;
    }
    break;
  }
  return PERL_constant_NOTFOUND;
}

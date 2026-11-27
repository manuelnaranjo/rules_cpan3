sv_setpv(config, "-DHAVE_DEV_PTMX -DHAVE_GETPT -DHAVE_GRANTPT -DHAVE_OPENPTY -DHAVE_POSIX_OPENPT -DHAVE_PTSNAME -DHAVE_PTSNAME_R -DHAVE_PTY_H -DHAVE_SIGACTION -DHAVE_STRLCPY -DHAVE_TERMIOS_H -DHAVE_TTYNAME -DHAVE_UNLOCKPT");
#ifdef B0
newCONSTSUB(stash, "B0", newSViv(B0));
#else
newCONSTSUB(stash, "B0", newSV(0));
#endif
#ifdef B110
newCONSTSUB(stash, "B110", newSViv(B110));
#else
newCONSTSUB(stash, "B110", newSV(0));
#endif
#ifdef B115200
newCONSTSUB(stash, "B115200", newSViv(B115200));
#else
newCONSTSUB(stash, "B115200", newSV(0));
#endif
#ifdef B1200
newCONSTSUB(stash, "B1200", newSViv(B1200));
#else
newCONSTSUB(stash, "B1200", newSV(0));
#endif
#ifdef B134
newCONSTSUB(stash, "B134", newSViv(B134));
#else
newCONSTSUB(stash, "B134", newSV(0));
#endif
#ifdef B150
newCONSTSUB(stash, "B150", newSViv(B150));
#else
newCONSTSUB(stash, "B150", newSV(0));
#endif
#ifdef B153600
newCONSTSUB(stash, "B153600", newSViv(B153600));
#else
newCONSTSUB(stash, "B153600", newSV(0));
#endif
#ifdef B1800
newCONSTSUB(stash, "B1800", newSViv(B1800));
#else
newCONSTSUB(stash, "B1800", newSV(0));
#endif
#ifdef B19200
newCONSTSUB(stash, "B19200", newSViv(B19200));
#else
newCONSTSUB(stash, "B19200", newSV(0));
#endif
#ifdef B200
newCONSTSUB(stash, "B200", newSViv(B200));
#else
newCONSTSUB(stash, "B200", newSV(0));
#endif
#ifdef B230400
newCONSTSUB(stash, "B230400", newSViv(B230400));
#else
newCONSTSUB(stash, "B230400", newSV(0));
#endif
#ifdef B2400
newCONSTSUB(stash, "B2400", newSViv(B2400));
#else
newCONSTSUB(stash, "B2400", newSV(0));
#endif
#ifdef B300
newCONSTSUB(stash, "B300", newSViv(B300));
#else
newCONSTSUB(stash, "B300", newSV(0));
#endif
#ifdef B307200
newCONSTSUB(stash, "B307200", newSViv(B307200));
#else
newCONSTSUB(stash, "B307200", newSV(0));
#endif
#ifdef B38400
newCONSTSUB(stash, "B38400", newSViv(B38400));
#else
newCONSTSUB(stash, "B38400", newSV(0));
#endif
#ifdef B460800
newCONSTSUB(stash, "B460800", newSViv(B460800));
#else
newCONSTSUB(stash, "B460800", newSV(0));
#endif
#ifdef B4800
newCONSTSUB(stash, "B4800", newSViv(B4800));
#else
newCONSTSUB(stash, "B4800", newSV(0));
#endif
#ifdef B50
newCONSTSUB(stash, "B50", newSViv(B50));
#else
newCONSTSUB(stash, "B50", newSV(0));
#endif
#ifdef B57600
newCONSTSUB(stash, "B57600", newSViv(B57600));
#else
newCONSTSUB(stash, "B57600", newSV(0));
#endif
#ifdef B600
newCONSTSUB(stash, "B600", newSViv(B600));
#else
newCONSTSUB(stash, "B600", newSV(0));
#endif
#ifdef B75
newCONSTSUB(stash, "B75", newSViv(B75));
#else
newCONSTSUB(stash, "B75", newSV(0));
#endif
#ifdef B76800
newCONSTSUB(stash, "B76800", newSViv(B76800));
#else
newCONSTSUB(stash, "B76800", newSV(0));
#endif
#ifdef B9600
newCONSTSUB(stash, "B9600", newSViv(B9600));
#else
newCONSTSUB(stash, "B9600", newSV(0));
#endif
#ifdef BRKINT
newCONSTSUB(stash, "BRKINT", newSViv(BRKINT));
#else
newCONSTSUB(stash, "BRKINT", newSV(0));
#endif
#ifdef BS0
newCONSTSUB(stash, "BS0", newSViv(BS0));
#else
newCONSTSUB(stash, "BS0", newSV(0));
#endif
#ifdef BS1
newCONSTSUB(stash, "BS1", newSViv(BS1));
#else
newCONSTSUB(stash, "BS1", newSV(0));
#endif
#ifdef BSDLY
newCONSTSUB(stash, "BSDLY", newSViv(BSDLY));
#else
newCONSTSUB(stash, "BSDLY", newSV(0));
#endif
#ifdef CBAUD
newCONSTSUB(stash, "CBAUD", newSViv(CBAUD));
#else
newCONSTSUB(stash, "CBAUD", newSV(0));
#endif
newCONSTSUB(stash, "CBAUDEXT", newSV(0));
#ifdef CBRK
newCONSTSUB(stash, "CBRK", newSViv(CBRK));
#else
newCONSTSUB(stash, "CBRK", newSV(0));
#endif
newCONSTSUB(stash, "CCTS_OFLOW", newSV(0));
newCONSTSUB(stash, "CDEL", newSV(0));
#ifdef CDSUSP
newCONSTSUB(stash, "CDSUSP", newSViv(CDSUSP));
#else
newCONSTSUB(stash, "CDSUSP", newSV(0));
#endif
#ifdef CEOF
newCONSTSUB(stash, "CEOF", newSViv(CEOF));
#else
newCONSTSUB(stash, "CEOF", newSV(0));
#endif
#ifdef CEOL
newCONSTSUB(stash, "CEOL", newSViv(CEOL));
#else
newCONSTSUB(stash, "CEOL", newSV(0));
#endif
newCONSTSUB(stash, "CEOL2", newSV(0));
#ifdef CEOT
newCONSTSUB(stash, "CEOT", newSViv(CEOT));
#else
newCONSTSUB(stash, "CEOT", newSV(0));
#endif
#ifdef CERASE
newCONSTSUB(stash, "CERASE", newSViv(CERASE));
#else
newCONSTSUB(stash, "CERASE", newSV(0));
#endif
newCONSTSUB(stash, "CESC", newSV(0));
#ifdef CFLUSH
newCONSTSUB(stash, "CFLUSH", newSViv(CFLUSH));
#else
newCONSTSUB(stash, "CFLUSH", newSV(0));
#endif
#ifdef CIBAUD
newCONSTSUB(stash, "CIBAUD", newSViv(CIBAUD));
#else
newCONSTSUB(stash, "CIBAUD", newSV(0));
#endif
newCONSTSUB(stash, "CIBAUDEXT", newSV(0));
#ifdef CINTR
newCONSTSUB(stash, "CINTR", newSViv(CINTR));
#else
newCONSTSUB(stash, "CINTR", newSV(0));
#endif
#ifdef CKILL
newCONSTSUB(stash, "CKILL", newSViv(CKILL));
#else
newCONSTSUB(stash, "CKILL", newSV(0));
#endif
#ifdef CLNEXT
newCONSTSUB(stash, "CLNEXT", newSViv(CLNEXT));
#else
newCONSTSUB(stash, "CLNEXT", newSV(0));
#endif
#ifdef CLOCAL
newCONSTSUB(stash, "CLOCAL", newSViv(CLOCAL));
#else
newCONSTSUB(stash, "CLOCAL", newSV(0));
#endif
newCONSTSUB(stash, "CNSWTCH", newSV(0));
newCONSTSUB(stash, "CNUL", newSV(0));
#ifdef CQUIT
newCONSTSUB(stash, "CQUIT", newSViv(CQUIT));
#else
newCONSTSUB(stash, "CQUIT", newSV(0));
#endif
#ifdef CR0
newCONSTSUB(stash, "CR0", newSViv(CR0));
#else
newCONSTSUB(stash, "CR0", newSV(0));
#endif
#ifdef CR1
newCONSTSUB(stash, "CR1", newSViv(CR1));
#else
newCONSTSUB(stash, "CR1", newSV(0));
#endif
#ifdef CR2
newCONSTSUB(stash, "CR2", newSViv(CR2));
#else
newCONSTSUB(stash, "CR2", newSV(0));
#endif
#ifdef CR3
newCONSTSUB(stash, "CR3", newSViv(CR3));
#else
newCONSTSUB(stash, "CR3", newSV(0));
#endif
#ifdef CRDLY
newCONSTSUB(stash, "CRDLY", newSViv(CRDLY));
#else
newCONSTSUB(stash, "CRDLY", newSV(0));
#endif
#ifdef CREAD
newCONSTSUB(stash, "CREAD", newSViv(CREAD));
#else
newCONSTSUB(stash, "CREAD", newSV(0));
#endif
#ifdef CRPRNT
newCONSTSUB(stash, "CRPRNT", newSViv(CRPRNT));
#else
newCONSTSUB(stash, "CRPRNT", newSV(0));
#endif
#ifdef CRTSCTS
newCONSTSUB(stash, "CRTSCTS", newSViv(CRTSCTS));
#else
newCONSTSUB(stash, "CRTSCTS", newSV(0));
#endif
newCONSTSUB(stash, "CRTSXOFF", newSV(0));
newCONSTSUB(stash, "CRTS_IFLOW", newSV(0));
#ifdef CS5
newCONSTSUB(stash, "CS5", newSViv(CS5));
#else
newCONSTSUB(stash, "CS5", newSV(0));
#endif
#ifdef CS6
newCONSTSUB(stash, "CS6", newSViv(CS6));
#else
newCONSTSUB(stash, "CS6", newSV(0));
#endif
#ifdef CS7
newCONSTSUB(stash, "CS7", newSViv(CS7));
#else
newCONSTSUB(stash, "CS7", newSV(0));
#endif
#ifdef CS8
newCONSTSUB(stash, "CS8", newSViv(CS8));
#else
newCONSTSUB(stash, "CS8", newSV(0));
#endif
#ifdef CSIZE
newCONSTSUB(stash, "CSIZE", newSViv(CSIZE));
#else
newCONSTSUB(stash, "CSIZE", newSV(0));
#endif
#ifdef CSTART
newCONSTSUB(stash, "CSTART", newSViv(CSTART));
#else
newCONSTSUB(stash, "CSTART", newSV(0));
#endif
#ifdef CSTOP
newCONSTSUB(stash, "CSTOP", newSViv(CSTOP));
#else
newCONSTSUB(stash, "CSTOP", newSV(0));
#endif
#ifdef CSTOPB
newCONSTSUB(stash, "CSTOPB", newSViv(CSTOPB));
#else
newCONSTSUB(stash, "CSTOPB", newSV(0));
#endif
#ifdef CSUSP
newCONSTSUB(stash, "CSUSP", newSViv(CSUSP));
#else
newCONSTSUB(stash, "CSUSP", newSV(0));
#endif
newCONSTSUB(stash, "CSWTCH", newSV(0));
#ifdef CWERASE
newCONSTSUB(stash, "CWERASE", newSViv(CWERASE));
#else
newCONSTSUB(stash, "CWERASE", newSV(0));
#endif
newCONSTSUB(stash, "DEFECHO", newSV(0));
newCONSTSUB(stash, "DIOC", newSV(0));
newCONSTSUB(stash, "DIOCGETP", newSV(0));
newCONSTSUB(stash, "DIOCSETP", newSV(0));
newCONSTSUB(stash, "DOSMODE", newSV(0));
#ifdef ECHO
newCONSTSUB(stash, "ECHO", newSViv(ECHO));
#else
newCONSTSUB(stash, "ECHO", newSV(0));
#endif
#ifdef ECHOCTL
newCONSTSUB(stash, "ECHOCTL", newSViv(ECHOCTL));
#else
newCONSTSUB(stash, "ECHOCTL", newSV(0));
#endif
#ifdef ECHOE
newCONSTSUB(stash, "ECHOE", newSViv(ECHOE));
#else
newCONSTSUB(stash, "ECHOE", newSV(0));
#endif
#ifdef ECHOK
newCONSTSUB(stash, "ECHOK", newSViv(ECHOK));
#else
newCONSTSUB(stash, "ECHOK", newSV(0));
#endif
#ifdef ECHOKE
newCONSTSUB(stash, "ECHOKE", newSViv(ECHOKE));
#else
newCONSTSUB(stash, "ECHOKE", newSV(0));
#endif
#ifdef ECHONL
newCONSTSUB(stash, "ECHONL", newSViv(ECHONL));
#else
newCONSTSUB(stash, "ECHONL", newSV(0));
#endif
#ifdef ECHOPRT
newCONSTSUB(stash, "ECHOPRT", newSViv(ECHOPRT));
#else
newCONSTSUB(stash, "ECHOPRT", newSV(0));
#endif
#ifdef EXTA
newCONSTSUB(stash, "EXTA", newSViv(EXTA));
#else
newCONSTSUB(stash, "EXTA", newSV(0));
#endif
#ifdef EXTB
newCONSTSUB(stash, "EXTB", newSViv(EXTB));
#else
newCONSTSUB(stash, "EXTB", newSV(0));
#endif
#ifdef FF0
newCONSTSUB(stash, "FF0", newSViv(FF0));
#else
newCONSTSUB(stash, "FF0", newSV(0));
#endif
#ifdef FF1
newCONSTSUB(stash, "FF1", newSViv(FF1));
#else
newCONSTSUB(stash, "FF1", newSV(0));
#endif
#ifdef FFDLY
newCONSTSUB(stash, "FFDLY", newSViv(FFDLY));
#else
newCONSTSUB(stash, "FFDLY", newSV(0));
#endif
newCONSTSUB(stash, "FIORDCHK", newSV(0));
#ifdef FLUSHO
newCONSTSUB(stash, "FLUSHO", newSViv(FLUSHO));
#else
newCONSTSUB(stash, "FLUSHO", newSV(0));
#endif
#ifdef HUPCL
newCONSTSUB(stash, "HUPCL", newSViv(HUPCL));
#else
newCONSTSUB(stash, "HUPCL", newSV(0));
#endif
#ifdef ICANON
newCONSTSUB(stash, "ICANON", newSViv(ICANON));
#else
newCONSTSUB(stash, "ICANON", newSV(0));
#endif
#ifdef ICRNL
newCONSTSUB(stash, "ICRNL", newSViv(ICRNL));
#else
newCONSTSUB(stash, "ICRNL", newSV(0));
#endif
#ifdef IEXTEN
newCONSTSUB(stash, "IEXTEN", newSViv(IEXTEN));
#else
newCONSTSUB(stash, "IEXTEN", newSV(0));
#endif
#ifdef IGNBRK
newCONSTSUB(stash, "IGNBRK", newSViv(IGNBRK));
#else
newCONSTSUB(stash, "IGNBRK", newSV(0));
#endif
#ifdef IGNCR
newCONSTSUB(stash, "IGNCR", newSViv(IGNCR));
#else
newCONSTSUB(stash, "IGNCR", newSV(0));
#endif
#ifdef IGNPAR
newCONSTSUB(stash, "IGNPAR", newSViv(IGNPAR));
#else
newCONSTSUB(stash, "IGNPAR", newSV(0));
#endif
#ifdef IMAXBEL
newCONSTSUB(stash, "IMAXBEL", newSViv(IMAXBEL));
#else
newCONSTSUB(stash, "IMAXBEL", newSV(0));
#endif
#ifdef INLCR
newCONSTSUB(stash, "INLCR", newSViv(INLCR));
#else
newCONSTSUB(stash, "INLCR", newSV(0));
#endif
#ifdef INPCK
newCONSTSUB(stash, "INPCK", newSViv(INPCK));
#else
newCONSTSUB(stash, "INPCK", newSV(0));
#endif
#ifdef ISIG
newCONSTSUB(stash, "ISIG", newSViv(ISIG));
#else
newCONSTSUB(stash, "ISIG", newSV(0));
#endif
#ifdef ISTRIP
newCONSTSUB(stash, "ISTRIP", newSViv(ISTRIP));
#else
newCONSTSUB(stash, "ISTRIP", newSV(0));
#endif
#ifdef IUCLC
newCONSTSUB(stash, "IUCLC", newSViv(IUCLC));
#else
newCONSTSUB(stash, "IUCLC", newSV(0));
#endif
#ifdef IXANY
newCONSTSUB(stash, "IXANY", newSViv(IXANY));
#else
newCONSTSUB(stash, "IXANY", newSV(0));
#endif
#ifdef IXOFF
newCONSTSUB(stash, "IXOFF", newSViv(IXOFF));
#else
newCONSTSUB(stash, "IXOFF", newSV(0));
#endif
#ifdef IXON
newCONSTSUB(stash, "IXON", newSViv(IXON));
#else
newCONSTSUB(stash, "IXON", newSV(0));
#endif
newCONSTSUB(stash, "KBENABLED", newSV(0));
newCONSTSUB(stash, "LDCHG", newSV(0));
newCONSTSUB(stash, "LDCLOSE", newSV(0));
newCONSTSUB(stash, "LDDMAP", newSV(0));
newCONSTSUB(stash, "LDEMAP", newSV(0));
newCONSTSUB(stash, "LDGETT", newSV(0));
newCONSTSUB(stash, "LDGMAP", newSV(0));
newCONSTSUB(stash, "LDIOC", newSV(0));
newCONSTSUB(stash, "LDNMAP", newSV(0));
newCONSTSUB(stash, "LDOPEN", newSV(0));
newCONSTSUB(stash, "LDSETT", newSV(0));
newCONSTSUB(stash, "LDSMAP", newSV(0));
newCONSTSUB(stash, "LOBLK", newSV(0));
#ifdef NCCS
newCONSTSUB(stash, "NCCS", newSViv(NCCS));
#else
newCONSTSUB(stash, "NCCS", newSV(0));
#endif
#ifdef NL0
newCONSTSUB(stash, "NL0", newSViv(NL0));
#else
newCONSTSUB(stash, "NL0", newSV(0));
#endif
#ifdef NL1
newCONSTSUB(stash, "NL1", newSViv(NL1));
#else
newCONSTSUB(stash, "NL1", newSV(0));
#endif
#ifdef NLDLY
newCONSTSUB(stash, "NLDLY", newSViv(NLDLY));
#else
newCONSTSUB(stash, "NLDLY", newSV(0));
#endif
#ifdef NOFLSH
newCONSTSUB(stash, "NOFLSH", newSViv(NOFLSH));
#else
newCONSTSUB(stash, "NOFLSH", newSV(0));
#endif
#ifdef OCRNL
newCONSTSUB(stash, "OCRNL", newSViv(OCRNL));
#else
newCONSTSUB(stash, "OCRNL", newSV(0));
#endif
#ifdef OFDEL
newCONSTSUB(stash, "OFDEL", newSViv(OFDEL));
#else
newCONSTSUB(stash, "OFDEL", newSV(0));
#endif
#ifdef OFILL
newCONSTSUB(stash, "OFILL", newSViv(OFILL));
#else
newCONSTSUB(stash, "OFILL", newSV(0));
#endif
#ifdef OLCUC
newCONSTSUB(stash, "OLCUC", newSViv(OLCUC));
#else
newCONSTSUB(stash, "OLCUC", newSV(0));
#endif
#ifdef ONLCR
newCONSTSUB(stash, "ONLCR", newSViv(ONLCR));
#else
newCONSTSUB(stash, "ONLCR", newSV(0));
#endif
#ifdef ONLRET
newCONSTSUB(stash, "ONLRET", newSViv(ONLRET));
#else
newCONSTSUB(stash, "ONLRET", newSV(0));
#endif
#ifdef ONOCR
newCONSTSUB(stash, "ONOCR", newSViv(ONOCR));
#else
newCONSTSUB(stash, "ONOCR", newSV(0));
#endif
#ifdef OPOST
newCONSTSUB(stash, "OPOST", newSViv(OPOST));
#else
newCONSTSUB(stash, "OPOST", newSV(0));
#endif
newCONSTSUB(stash, "PAGEOUT", newSV(0));
#ifdef PARENB
newCONSTSUB(stash, "PARENB", newSViv(PARENB));
#else
newCONSTSUB(stash, "PARENB", newSV(0));
#endif
newCONSTSUB(stash, "PAREXT", newSV(0));
#ifdef PARMRK
newCONSTSUB(stash, "PARMRK", newSViv(PARMRK));
#else
newCONSTSUB(stash, "PARMRK", newSV(0));
#endif
#ifdef PARODD
newCONSTSUB(stash, "PARODD", newSViv(PARODD));
#else
newCONSTSUB(stash, "PARODD", newSV(0));
#endif
#ifdef PENDIN
newCONSTSUB(stash, "PENDIN", newSViv(PENDIN));
#else
newCONSTSUB(stash, "PENDIN", newSV(0));
#endif
newCONSTSUB(stash, "RCV1EN", newSV(0));
newCONSTSUB(stash, "RTS_TOG", newSV(0));
#ifdef TAB0
newCONSTSUB(stash, "TAB0", newSViv(TAB0));
#else
newCONSTSUB(stash, "TAB0", newSV(0));
#endif
#ifdef TAB1
newCONSTSUB(stash, "TAB1", newSViv(TAB1));
#else
newCONSTSUB(stash, "TAB1", newSV(0));
#endif
#ifdef TAB2
newCONSTSUB(stash, "TAB2", newSViv(TAB2));
#else
newCONSTSUB(stash, "TAB2", newSV(0));
#endif
#ifdef TAB3
newCONSTSUB(stash, "TAB3", newSViv(TAB3));
#else
newCONSTSUB(stash, "TAB3", newSV(0));
#endif
#ifdef TABDLY
newCONSTSUB(stash, "TABDLY", newSViv(TABDLY));
#else
newCONSTSUB(stash, "TABDLY", newSV(0));
#endif
newCONSTSUB(stash, "TCDSET", newSV(0));
#ifdef TCFLSH
newCONSTSUB(stash, "TCFLSH", newSViv(TCFLSH));
#else
newCONSTSUB(stash, "TCFLSH", newSV(0));
#endif
#ifdef TCGETA
newCONSTSUB(stash, "TCGETA", newSViv(TCGETA));
#else
newCONSTSUB(stash, "TCGETA", newSV(0));
#endif
#ifdef TCGETS
newCONSTSUB(stash, "TCGETS", newSViv(TCGETS));
#else
newCONSTSUB(stash, "TCGETS", newSV(0));
#endif
#ifdef TCIFLUSH
newCONSTSUB(stash, "TCIFLUSH", newSViv(TCIFLUSH));
#else
newCONSTSUB(stash, "TCIFLUSH", newSV(0));
#endif
#ifdef TCIOFF
newCONSTSUB(stash, "TCIOFF", newSViv(TCIOFF));
#else
newCONSTSUB(stash, "TCIOFF", newSV(0));
#endif
#ifdef TCIOFLUSH
newCONSTSUB(stash, "TCIOFLUSH", newSViv(TCIOFLUSH));
#else
newCONSTSUB(stash, "TCIOFLUSH", newSV(0));
#endif
#ifdef TCION
newCONSTSUB(stash, "TCION", newSViv(TCION));
#else
newCONSTSUB(stash, "TCION", newSV(0));
#endif
#ifdef TCOFLUSH
newCONSTSUB(stash, "TCOFLUSH", newSViv(TCOFLUSH));
#else
newCONSTSUB(stash, "TCOFLUSH", newSV(0));
#endif
#ifdef TCOOFF
newCONSTSUB(stash, "TCOOFF", newSViv(TCOOFF));
#else
newCONSTSUB(stash, "TCOOFF", newSV(0));
#endif

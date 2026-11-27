/* PAM_config.h. Generated for Authen::PAM on Linux with linux-pam. */

/* Is the symbol PAM_AUTHTOKEN_REQD defined? */
/* #undef HAVE_PAM_AUTHTOKEN_REQD */

/* Is the symbol PAM_AUTHTOK_EXPIRED defined? */
#define HAVE_PAM_AUTHTOK_EXPIRED 1

/* Is the symbol PAM_AUTHTOK_RECOVER defined? */
/* #undef HAVE_PAM_AUTHTOK_RECOVER */

/* Is the symbol PAM_AUTHTOK_RECOVERY defined? */
/* #undef HAVE_PAM_AUTHTOK_RECOVERY */

/* Is the symbol PAM_BAD_ITEM defined? */
#define HAVE_PAM_BAD_ITEM 1

/* Is the symbol PAM_CONV_AGAIN defined? */
#define HAVE_PAM_CONV_AGAIN 1

/* Is the symbol PAM_CRED_DELETE defined? */
/* #undef HAVE_PAM_CRED_DELETE */

/* Is the symbol PAM_CRED_ESTABLISH defined? */
/* #undef HAVE_PAM_CRED_ESTABLISH */

/* Is the symbol PAM_CRED_REFRESH defined? */
/* #undef HAVE_PAM_CRED_REFRESH */

/* Is the symbol PAM_CRED_REINITIALIZE defined? */
/* #undef HAVE_PAM_CRED_REINITIALIZE */

/* Is the symbol PAM_DELETE_CRED defined? */
#define HAVE_PAM_DELETE_CRED 1

/* Is the symbol PAM_ESTABLISH_CRED defined? */
#define HAVE_PAM_ESTABLISH_CRED 1

/* Define to 1 if you have the `pam_getenv' function. */
#define HAVE_PAM_GETENV 1

/* Is the symbol PAM_INCOMPLETE defined? */
#define HAVE_PAM_INCOMPLETE 1

/* Is the symbol PAM_MODULE_UNKNOWN defined? */
#define HAVE_PAM_MODULE_UNKNOWN 1

/* Is the symbol PAM_NEW_AUTHTOK_REQD defined? */
#define HAVE_PAM_NEW_AUTHTOK_REQD 1

/* pam_appl.h in /usr/include/pam */
/* #undef HAVE_PAM_PAM_APPL_H */

/* Is the symbol PAM_RADIO_TYPE defined? */
#define HAVE_PAM_RADIO_TYPE 1

/* Is the symbol PAM_REFRESH_CRED defined? */
#define HAVE_PAM_REFRESH_CRED 1

/* Is the symbol PAM_REINITIALIZE_CRED defined? */
#define HAVE_PAM_REINITIALIZE_CRED 1

/* pam_appl.h in /usr/include/security */
#define HAVE_SECURITY_PAM_APPL_H 1

/* Define to the address where bug reports for this package should be sent. */
#define PACKAGE_BUGREPORT ""

/* Define to the full name of this package. */
#define PACKAGE_NAME "Authen::PAM"

/* Define to the full name and version of this package. */
#define PACKAGE_STRING "Authen::PAM 0.16"

/* Define to the one symbol short name of this package. */
#define PACKAGE_TARNAME "Authen-PAM"

/* Define to the version of this package. */
#define PACKAGE_VERSION "0.16"

/* Checks if pam_strerror() takes a pam_handle */
#define PAM_STRERROR_NEEDS_PAMH 1

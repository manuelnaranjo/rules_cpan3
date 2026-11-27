#ifndef GRPC_PERL_CHANNEL_CREDENTIALS_H
#define GRPC_PERL_CHANNEL_CREDENTIALS_H

#include <grpc/grpc.h>
#include <grpc/grpc_security.h>
#include <grpc/credentials.h>

typedef struct {
  grpc_channel_credentials *wrapped;
} ChannelCredentialsCTX;

typedef ChannelCredentialsCTX* Grpc__XS__ChannelCredentials;

#endif

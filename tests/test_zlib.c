#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "zlib.h"

int main(void) {
    const char *ver = zlibVersion();
    printf("zlib version: %s\n", ver);
    assert(ver != NULL);
    assert(ver[0] == '1');

    const char *original = "Hermetic Perl CPAN rules consuming 3rdparty zlib from local BCR registry!";
    uLong orig_len = (uLong)(strlen(original) + 1);

    uLong bound = compressBound(orig_len);
    Bytef *compressed = (Bytef *)malloc(bound);
    assert(compressed != NULL);

    uLong comp_len = bound;
    int res = compress(compressed, &comp_len, (const Bytef *)original, orig_len);
    assert(res == Z_OK);
    printf("Compressed %lu bytes down to %lu bytes\n", orig_len, comp_len);

    Bytef *uncompressed = (Bytef *)malloc(orig_len);
    assert(uncompressed != NULL);

    uLong uncomp_len = orig_len;
    res = uncompress(uncompressed, &uncomp_len, compressed, comp_len);
    assert(res == Z_OK);
    assert(uncomp_len == orig_len);
    assert(strcmp((const char *)uncompressed, original) == 0);

    printf("Decompressed text matches original: %s\n", (const char *)uncompressed);

    free(compressed);
    free(uncompressed);

    printf("All zlib tests passed successfully!\n");
    return 0;
}

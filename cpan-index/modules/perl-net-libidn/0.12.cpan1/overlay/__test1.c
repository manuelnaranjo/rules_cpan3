#include <idna.h>
#include <stdio.h>
int main(void)
{
	char * output;
	int res;

	res = idna_to_ascii_8z("libidn", &output, 0);
	printf("%d-%s", res, output);

	return 0;
}

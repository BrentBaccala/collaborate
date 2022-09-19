#
# This file will be exec'ed by install-lambda.py.
#
# It should define a dictionary CONFIG that maps server names to dictionaries.
#
# Each server dictionary should contain entries 'fqdn' (a string),
# 'instances' (a list of strings, each an AWS instance ID),
# and 'keys' (a list of strings, each an openssh RSA public key)
#
# This data will get passed through to lambda_function.py, where it gets interpreted.

CONFIG = {
}

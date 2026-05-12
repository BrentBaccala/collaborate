#
# This file will be exec'ed by install-lambda.py.
#
# It should define a dictionary CONFIG that maps server names to dictionaries.
#
# Required fields per server:
#   'fqdn' (string)  -- DNS name of the BBB host (the primary instance)
#   'keys' (list)    -- openssh RSA public keys accepted for this server
#
# Instance selection -- specify any combination of the four fields below; the
# resulting sets are unioned, and the primary is always included:
#   'primary_instance' (string)            -- the BBB host that 'fqdn' resolves to;
#                                             its public IP gets DNS-checked and the
#                                             wait page redirects there.
#                                             Defaults to instances[0] if omitted.
#   'instances'        (list of strings)   -- additional explicit instance IDs.
#   'filters'          (list of dicts)     -- boto3 Filter spec, e.g.
#                                             [{"Name": "tag:AutoStart", "Values": ["x"]}]
#   'tags'             (dict[str, str])    -- shorthand: {"AutoStart": "x"} is expanded
#                                             into the tag filter above (AND across keys).
#
# Filter/tag resolution happens on every lambda invocation, so an instance
# tagged after deployment will be started on the next user join without
# redeploying. For symmetric stop-side behavior, use the same tag in
# ADDITIONAL_STOP_TAGS on the BBB host (see bbb-aws-hibernate.default).
#
# This data will get passed through to lambda_function.py, where it gets interpreted.

CONFIG = {
}

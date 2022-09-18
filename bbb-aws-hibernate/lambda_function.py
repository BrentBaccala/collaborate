#
# URL will look like: https://abcdef123.execute-api.us-east-2.amazonaws.com/my-function
#
# we'll use: https://abcdef123.execute-api.us-east-2.amazonaws.com/login?USER_JWT
#
# To redirect from https://login.freesoft.org/login/USER_JWT, we'll need some kind of static AWS content
# served from S3.
#
# We need this lambda role to have permission to start the instance
# We need to add "add_header Access-Control-Allow-Origin *;" to nginx location / on the BigBlueButton server
#
# According to https://aws.amazon.com/premiumsupport/knowledge-center/lambda-python-package-compatible/
# see also https://stackoverflow.com/a/63137370/1493790
#
# pip3 install --target package pyjwt
# pip3 install --target package serialization
#     (last command will show "ERROR: launchpadlib 1.10.13 requires testresources, which is not installed.")
# pip3 install --target package cryptography
# pip3 install --target package dnspython
# unzip -d package cffi-1.15.0-cp39-cp39-manylinux_2_12_x86_64.manylinux2010_x86_64.whl
#
# cd package; zip -r ../my-deployment-package.zip .
# zip -g my-deployment-package.zip lambda_function.py
#
# Command-line usage:
#
# aws lambda update-function-code --function-name login --zip-file fileb://my-deployment-package.zip --profile cosine
#
# To watch the output, pip3 install awslogs and then:
#    awslogs get /aws/lambda/login --profile=cosine
#
# Running the lambda function for the first time creates the log group.

import os
import jwt
import time
import json
import boto3
import requests
import dns.resolver
from cryptography.hazmat.primitives.serialization import load_ssh_public_key

region = os.environ['AWS_REGION']
ec2 = boto3.client('ec2', region_name=region)

# Environment variable CONFIG is a JSON dictionary mapping server names ('nam' in the JWT)
# to dictionaries with entries 'fqdn' (a string), 'instances' (a list of strings, each an AWS instance ID),
# and 'keys' (a list of strings, each an openssh RSA public key)

config = json.loads(os.environ['CONFIG'])

# Parse all of the SSH public keys once, when the lambda function loads.

for server in config:
    config[server]['keys'] = [load_ssh_public_key(key.encode()) for key in config[server]['keys']]

def authenticate(token):
    token_dict = jwt.decode(token, verify=False)
    name = token_dict.get('nam')
    if name in config:
        for key in config[name]['keys']:
            try:
                return jwt.decode(token, key = key, algorithms = ['RS512'])
            except:
                pass
    return None

# HTML spinner, from https://www.w3schools.com/howto/howto_css_loader.asp
#
# Before sending this to the client, the lambda function will replace {token} with the JWT,
# {nam} with the server name, and {dns} with the FQDN of the server.
#
# Upon loading, the spinner page will immediately call back to the lambda function using
# 'waitpage-{nam}' as its "token".  This special case is detected by the lambda function
# and causes it to wait for that instance to be running, and for a lookup on its DNS name
# to return the instance's public IP address.  Or it will timeout after 29 seconds.
# If it timeouts, the spinner page keeps retrying.  Once it returns success, the
# spinner page redirects to https://{dns}/login/{token} to login to the collaborate server.

wait_page=r"""<html>
<head>
<style>
body {
  background-color: #06172A;
}
.greeting {
  font-size: xxx-large;
  font-weight: bold;
  text-align: center;
  color: white;
  margin-bottom: 5%
}
.greeting2 {
  font-size: large;
  font-weight: bold;
  text-align: center;
  color: white;
  margin-bottom: 10%
}

.loader {
  border: 16px solid #0C1D30;
  border-top: 16px solid #3498db; /* Blue */
  border-radius: 50%;
  width: 120px;
  height: 120px;
  -webkit-animation: spin 2s linear infinite; /* Safari */
  animation: spin 2s linear infinite;
  margin-left: auto;
  margin-right: auto;
}

/* Safari */
@-webkit-keyframes spin {
  0% { -webkit-transform: rotate(0deg); }
  100% { -webkit-transform: rotate(360deg); }
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
<script>
function fn() {
    /* from https://stackoverflow.com/a/4033310/1493790 */
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.onreadystatechange = function() {
        if (xmlHttp.readyState == 4) {
            if (xmlHttp.status == 200)
                window.location.replace('https://{dns}/login/{token}');
            else if (xmlHttp.status == 503) {
                /* AWS API gateway has a hard timeout of 29 seconds and returns 503.  Retry. */
                xmlHttp.open("GET", "/login?waitpage-{nam}", true);
                xmlHttp.send();
            } else {
                for (element of document.getElementsByClassName('loader')) {
                    element.remove();
                }
                document.getElementById('greeting').innerHTML = "Error";
                document.getElementById('greeting2').innerHTML = xmlHttp.statusCode + " " + xmlHttp.statusText;
            }
        }
    }
    xmlHttp.onerror = function() {
        for (element of document.getElementsByClassName('loader')) {
            element.remove();
        }
        document.getElementById('greeting2').innerHTML = 'Sorry, something went wrong on the network level!';
    }
    xmlHttp.ontimeout = function() {
        for (element of document.getElementsByClassName('loader')) {
            element.remove();
        }
        document.getElementById('greeting2').innerHTML = 'Timeout!';
    }
    xmlHttp.open("GET", '/login?waitpage-{nam}', true); // true for asynchronous
    xmlHttp.send();
}
/* setTimeout(fn, 3000); */
fn()
</script>
</head>
<body>
<div id="greeting" class="greeting">Welcome!</div>
<div id="greeting2" class="greeting2">Please wait for your collaborate server to start</div>
<div class="loader"></div>
</body>
</html>
"""

error_page=r"""<html>
<head>
<style>
.greeting {
  font-size: xxx-large;
  font-weight: bold;
  text-align: center;
  margin-bottom: 5%
}
.greeting2 {
  font-size: large;
  font-weight: bold;
  text-align: center;
  margin-bottom: 10%
}
</style>
</head>
<body>
<div class="greeting">Sorry!</div>
<div class="greeting2">{error}</div>
</body>
</html>
"""

def lambda_handler(event, context):
    token = event['rawQueryString']
    if token.startswith('waitpage-'):
        name = token[9:]
        print('waiting for instance to run')
        instances = config[name]['instances']
        # XXX - make this check all the instances in the list, not just the first one
        while ec2.describe_instances(InstanceIds=instances)['Reservations'][0]['Instances'][0]['State']['Name'] != 'running':
            time.sleep(1)
        print('instance running')
        public_ip_addr = ec2.describe_instances(InstanceIds=instances)['Reservations'][0]['Instances'][0]['PublicIpAddress']
        print('instance running on', public_ip_addr)
        my_resolver = dns.resolver.Resolver()
        # I put this here to make sure we're querying the domain's authoritative server, but
        # hardwiring it like this only works for Google Domains
        # my_resolver.nameservers = ['216.239.32.108']    # ns-cloud-c1.googledomains.com
        dnsname = config[name]['fqdn']
        while my_resolver.resolve(dnsname)[0].address != public_ip_addr:
            time.sleep(1)
        print('dns right')
        url = 'https://{}/bigbluebutton/api'.format(dnsname)
        ans = requests.get(url)
        print(ans)
        while not ans.headers['Content-Type'].startswith('text/xml'):
            time.sleep(1)
            ans = requests.get(url)
            print(ans)
        return {'statusCode': 200, 'headers': {'Content-Type': 'text/plain'}, 'body': '' }
    else:
        jwt = authenticate(token)
        if jwt:
            instances = config[jwt['nam']]['instances']
            if ec2.describe_instances(InstanceIds=instances)['Reservations'][0]['Instances'][0]['State']['Name'] != 'running':
                try:
                    ec2.start_instances(InstanceIds=instances)
                except Exception as ex:
                    error_page_formatted = error_page.replace('{error}', str(ex))
                    return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': error_page_formatted }
                print('started your instances: ' + str(instances))
            # redirect to a URL
            #    return {'statusCode': 302, 'headers': {'Location': 'https://freesoft.org/'}}
            # or just return the spinner page here and it redirects to our goal
            wait_page_formatted = wait_page.replace('{token}', token).replace('{nam}', jwt['nam']).replace('{dns}', config[jwt['nam']]['fqdn'])
            return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': wait_page_formatted }
        else:
            error_page_formatted = error_page.replace('{error}', 'Your authentication key was not accepted')
            return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': error_page_formatted }

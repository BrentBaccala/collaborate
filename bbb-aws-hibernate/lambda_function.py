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
import botocore
import cfnresponse
import requests
import dns.resolver
from cryptography.hazmat.primitives.serialization import load_ssh_public_key
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend

region = os.environ['AWS_REGION']
ec2 = boto3.client('ec2', region_name=region)

def authenticate(config, token):
    try:
        token_dict = jwt.decode(token, verify=False)
    except:
        return None
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
<div id="greeting2" class="greeting2">{message}</div>
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

# I use curly braces so much in the Javascript, I don't want to double
# them all up to escape them, so I used a "limited_format" function
# that only replaces the strings specified in the keyword arguments.

def limited_format(string, **kwargs):
    for k,v in kwargs.items():
        string = string.replace('{' + k + '}', v)
    return string

def lambda_handler(event, context):
  # Environment variable CONFIG is a JSON dictionary mapping server names ('nam' in the JWT)
  # to dictionaries with entries 'fqdn' (a string), 'instances' (a list of strings, each an AWS instance ID),
  # and 'keys' (a list of strings, each an openssh RSA public key)

  config = json.loads(os.environ['CONFIG'])

  # XXX - Parse all of the SSH public keys once, when the lambda function loads.
  # XXX - I've moved this into the lambda_handler code since we don't have a CONFIG variable when used to generate keys

  for server in config:
      config[server]['keys'] = [load_ssh_public_key(key.encode()) for key in config[server]['keys']]

  try:
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
        dnsname = config[name]['fqdn']

        # I put this here to make sure we're querying the domain's authoritative server,
        # to avoid caching an old response for 60 seconds
        domain = dns.name.from_text(dnsname).parent()
        my_resolver.nameservers = [a.address for ns in my_resolver.query(domain, rdtype='NS').rrset for a in my_resolver.query(str(ns.target)).rrset]

        last_dns_IP = None
        dns_IP = None
        while dns_IP != public_ip_addr:
            dns_IP = my_resolver.resolve(dnsname)[0].address
            if dns_IP != public_ip_addr:
                if dns_IP != last_dns_IP:
                    print('dns resolves wrong:', dns_IP)
                    last_dns_IP = dns_IP
                time.sleep(1)
        print('dns right')
        url = 'https://{}/bigbluebutton/api'.format(dnsname)
        ans = requests.get(url)
        while not ans.headers['Content-Type'].startswith('text/xml'):
            time.sleep(1)
            ans = requests.get(url)
            print(ans)
        return {'statusCode': 200, 'headers': {'Content-Type': 'text/plain'}, 'body': '' }
    else:
        jwt = authenticate(config, token)
        if jwt:
            instances = config[jwt['nam']]['instances']
            instances_to_start = []
            # Depending on our AWS permissions, we might be able to perform either
            # a DescribeInstanceStatus or a DescribeInstances, but not the other
            try:
                instance_statuses = ec2.describe_instance_status(InstanceIds=instances, IncludeAllInstances=True)['InstanceStatuses']
                instances_to_start = [instance['InstanceId'] for instance in instance_statuses if instance['InstanceState']['Name'] != 'running']

            except Exception:
                if ec2.describe_instances(InstanceIds=instances)['Reservations'][0]['Instances'][0]['State']['Name'] != 'running':
                    instances_to_start = instances


            if not instances_to_start:
                    wait_message = "Please wait"
            else:
                if jwt['role'] == 'm' or jwt['role'] == 'M':
                    wait_message = "Please wait for your collaborate server to start"
                else:
                    instances_to_start = []
                    wait_message = "Please wait for a moderator to start your meeting"

            if instances_to_start:
                try:
                    try:
                        ec2.start_instances(InstanceIds=instances_to_start)
                    except botocore.exceptions.ClientError:
                        # If we couldn't start all of the instances, make sure we
                        # start the first one (presumably the videoconference server),
                        # then optionally try to start the rest
                        ec2.start_instances(InstanceIds=instances_to_start[0:1])
                        for instance in instances_to_start[1:]:
                            try:
                                ec2.start_instances(InstanceIds=[instance])
                            except botocore.exceptions.ClientError:
                                pass
                except Exception as ex:
                    error_page_formatted = limited_format(error_page, error=str(ex))
                    return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': error_page_formatted }
                print('started your instances: ' + str(instances))
            # redirect to a URL
            #    return {'statusCode': 302, 'headers': {'Location': 'https://freesoft.org/'}}
            # or just return the spinner page here and it redirects to our goal
            wait_page_formatted = limited_format(wait_page,
                                                 message = wait_message,
                                                 token = token,
                                                 nam = jwt['nam'],
                                                 dns = config[jwt['nam']]['fqdn'])
            return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': wait_page_formatted }
        else:
            error_page_formatted = limited_format(error_page, error='Your authentication key was not accepted')
            return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': error_page_formatted }
  except Exception as ex:
    error_page_formatted = limited_format(error_page, error=str(ex))
    return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': error_page_formatted }


def generate_key_pair(event, context):
  try:
    key = rsa.generate_private_key(
	backend=crypto_default_backend(),
	public_exponent=65537,
	key_size=2048
    )
    private_key = key.private_bytes(
	crypto_serialization.Encoding.PEM,
	crypto_serialization.PrivateFormat.OpenSSH,
	crypto_serialization.NoEncryption()
    )
    public_key = key.public_key().public_bytes(
	crypto_serialization.Encoding.OpenSSH,
	crypto_serialization.PublicFormat.OpenSSH
    )
    responseData = {}
    responseData['PublicKey'] = public_key.decode()
    responseData['PrivateKey'] = private_key.decode()
    cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, "CustomResourcePhysicalID")
  except Exception as ex:
    cfnresponse.send(event, context, cfnresponse.FAILED, reason=str(ex))

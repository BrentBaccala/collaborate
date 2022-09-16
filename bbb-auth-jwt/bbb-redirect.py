
import boto3

aws_region = 'us-east-1'
instance_id = 'i-04dd04574eaa2ea4b'
dns_name = 'collaborate-01.freesoft.org'

WAIT_URL = 'https://' + socket.getfqdn() + '/wait.html'

REMOTE_CHECK_URL = f"https://{dns_name}/bigbluebutton/api"
REMOTE_LOGIN_URL = f"https://{dns_name}/login/"

def ec2():
    if not hasattr(ec2, 'retval'):
        session = boto3.Session(region_name = aws_region)
        ec2.retval = session.client('ec2')
    return ec2.retval

def is_remote_running():
    result = ec2().describe_instance_status(InstanceIds=[instance_id], IncludeAllInstances=True)
    return result['InstanceStatuses'][0]['InstanceState']['Name'] == 'running'

def start_remote():
    ec2().start_instances(InstanceIds=[instance_id])

def redirect(JWT):
    if is_remote_running():
        response = REMOTE_LOGIN_URL + JWT
    else:
        start_remote()
        response = WAIT_URL + '?' + urllib.parse.urlencode({'pingUrl' : REMOTE_CHECK_URL,
                                                            'targetUrl' : REMOTE_LOGIN_URL + JWT})
    return response

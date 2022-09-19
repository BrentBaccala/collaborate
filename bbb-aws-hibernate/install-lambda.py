#!/usr/bin/env python3
#
# Use AWS boto3 library to install a lambda function to autostart an instance

import os
import sys
import boto3
import json
import base64
import hashlib

exec(open('configuration.py').read())

if 'AWS_PROFILE' not in os.environ:
    print('Specify an AWS profile name in the AWS_PROFILE environment variable')
    exit()

assert len(json.dumps(CONFIG)) <= 4096

environment = { "Variables" : {"CONFIG" : json.dumps(CONFIG)} }

sts = boto3.client('sts')
apigw = boto3.client('apigatewayv2')
iam = boto3.client('iam')
l = boto3.client('lambda')

ACCOUNT = sts.get_caller_identity()['Account']
#print('Account', ACCOUNT)

login_role_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["ec2:DescribeInstances", "ec2:StartInstances"],
            "Resource": "*"
        }
    ]
}

if 'delete-policy' in sys.argv:
    POLICY_ARN = next(policy['Arn'] for policy in iam.list_policies(Scope='Local')['Policies'] if policy['PolicyName'] == 'login')
    iam.delete_policy(PolicyArn = POLICY_ARN)

try:
    POLICY_ARN = next(policy['Arn'] for policy in iam.list_policies(Scope='Local')['Policies'] if policy['PolicyName'] == 'login')
except StopIteration:
    print('Creating policy login')
    POLICY_ARN = iam.create_policy(PolicyName = 'login', PolicyDocument = json.dumps(login_role_policy))['Policy']['Arn']

if 'delete-role' in sys.argv:
    iam.delete_role(RoleName = 'login')

lambda_role_policy = {
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}

try:
    ROLE = iam.get_role(RoleName = 'login')['Role']['Arn']
except iam.exceptions.NoSuchEntityException:
    print('Creating role login')
    ROLE = iam.create_role(RoleName = 'login', AssumeRolePolicyDocument = json.dumps(lambda_role_policy))['Role']['Arn']

if 'delete-function' in sys.argv:
    l.delete_function(FunctionName='login')

with open('aws-login/my-deployment-package.zip', 'rb') as f:
    zipfile = f.read()

try:
    lambda_function = l.get_function(FunctionName='login')['Configuration']
    current_AWS_sha256 = lambda_function['CodeSha256']
    m = hashlib.sha256()
    m.update(zipfile)
    local_code_sha256 = base64.b64encode(m.digest()).decode()
    if current_AWS_sha256 != local_code_sha256:
        print('Updating function login')
        l.update_function_code(FunctionName = 'login', ZipFile=zipfile)
    FUNCTION_ARN = lambda_function['FunctionArn']
except l.exceptions.ResourceNotFoundException:
    print('Creating function login')
    FUNCTION_ARN = l.create_function(FunctionName='login', Role=ROLE, Runtime='python3.9',
                                     PackageType='Zip', Code={'ZipFile': zipfile},
                                     Environment=environment,
                                     Handler='lambda_function.lambda_handler', Timeout=60)['FunctionArn']

current_AWS_environment = l.get_function_configuration(FunctionName='login')['Environment']
if current_AWS_environment != environment:
    print('updating login function environment')
    l.update_function_configuration(FunctionName = 'login', Environment = environment)

if 'delete-api' in sys.argv:
    try:
        API_ID = next(item['ApiId'] for item in apigw.get_apis()['Items'] if item['Name'] == 'login')
    except StopIteration:
        print("API 'login' not found in this region")
        sys.exit(1)

    for ROUTE_ID in (item['RouteId'] for item in apigw.get_routes(ApiId=API_ID)['Items']):
        print('Deleting route', ROUTE_ID)
        apigw.delete_route(ApiId=API_ID, RouteId=ROUTE_ID)

    # Doesn't seem to be needed; throws an exception claiming that the route hasn't been deleted
    #for INTEGRATION_ID in (item['IntegrationId'] for item in apigw.get_integrations(ApiId=API_ID)['Items']):
    #    print('Deleting integration', INTEGRATION_ID)
    #    apigw.delete_integration(ApiId=API_ID, IntegrationId=INTEGRATION_ID)

    print('Deleting API', API_ID)
    apigw.delete_api(ApiId=API_ID)

try:
    URL = next(item['ApiEndpoint'] for item in apigw.get_apis()['Items'] if item['Name'] == 'login')
except StopIteration:
    print('Creating API login')
    API = apigw.create_api(Name='login', ProtocolType='HTTP', Target=FUNCTION_ARN, RouteKey='ANY /login')
    API_ID = API['ApiId']
    URL = API['ApiEndpoint']

    REGION = boto3.DEFAULT_SESSION.region_name
    STATEMENT_ID = 'apigateway-get-{}'.format(REGION)
    SOURCE_ARN = "arn:aws:execute-api:{}:{}:{}/*/*/login".format(REGION, ACCOUNT, API_ID)
    l.add_permission(FunctionName='login', StatementId=STATEMENT_ID, Action='lambda:InvokeFunction',
        Principal='apigateway.amazonaws.com', SourceArn=SOURCE_ARN)

print('URL', URL + '/login')

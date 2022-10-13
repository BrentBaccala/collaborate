#!/usr/bin/env python3
#
# Use AWS boto3 library to install a lambda function to autostart an instance
#
# Needs to be run on an account with an AWS access key with suitable permission.
#
# Creates a policy giving permission to describe and start EC2 instances,
# creates a role with that policy as its primary permission, creates
# a lambda function that runs with that role, and creates an API gateway
# that runs that lambda function when a certain URL is requested.

import os
import sys
import boto3
import json
import base64
import hashlib

import sqlite3

if 'AWS_PROFILE' not in os.environ:
    print('Specify an AWS profile name in the AWS_PROFILE environment variable')
    exit()

# the filename of the zip file containing the AWS deployment package
DEPLOYMENT_PACKAGE = 'build/deployment-package.zip'

# the filename of the SQLite3 database used to relay the API gateway URLs to bbb-mklogin
SQLITE3_DATABASE = '../bbb-auth.sqlite'

# name of the API gateway endpoint (the part that is tied to a URL)
API_NAME = 'login'

# name of the lambda function
FUNCTION_NAME = 'login'

# name of the policy that grants DescribeInstances and StartInstances permissions
POLICY_NAME = 'login'

# name of the role that the lambda function will run as
ROLE_NAME = 'login'

exec(open('configuration.py').read())

assert len(json.dumps(CONFIG)) <= 4096

environment = { "Variables" : {"CONFIG" : json.dumps(CONFIG)} }

sts = boto3.client('sts')
apigw = boto3.client('apigatewayv2')
iam = boto3.client('iam')
l = boto3.client('lambda')

ACCOUNT = sts.get_caller_identity()['Account']

# Policy that specifies permissions given to the role ROLE_NAME, and by extension to the lambda function

role_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["ec2:DescribeInstances", "ec2:StartInstances"],
            "Resource": "*"
        }
    ]
}

# Policy that lets lambda functions assume the role ROLE_NAME

assume_role_policy = {
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

if 'delete-api' in sys.argv or 'delete-region' in sys.argv or 'delete-everything' in sys.argv:
    try:
        API_ID = next(item['ApiId'] for item in apigw.get_apis()['Items'] if item['Name'] == API_NAME)
    except StopIteration:
        print(f"API '{API_NAME}' not found in this region")
        sys.exit(1)

    print('Deleting all routes in API', API_ID)
    for ROUTE_ID in (item['RouteId'] for item in apigw.get_routes(ApiId=API_ID)['Items']):
        print('Deleting route', ROUTE_ID)
        apigw.delete_route(ApiId=API_ID, RouteId=ROUTE_ID)

    # Doesn't seem to be needed; throws an exception claiming that the route hasn't been deleted
    #for INTEGRATION_ID in (item['IntegrationId'] for item in apigw.get_integrations(ApiId=API_ID)['Items']):
    #    print('Deleting integration', INTEGRATION_ID)
    #    apigw.delete_integration(ApiId=API_ID, IntegrationId=INTEGRATION_ID)

    print('Deleting API', API_ID)
    apigw.delete_api(ApiId=API_ID)

if 'delete-function' in sys.argv or 'delete-region' in sys.argv or 'delete-everything' in sys.argv:
    print('Deleting lambda function', FUNCTION_NAME)
    l.delete_function(FunctionName=FUNCTION_NAME)

if 'delete-role' in sys.argv or 'delete-everything' in sys.argv:
    print('Detaching role policies')
    POLICY_ARN = next(policy['Arn'] for policy in iam.list_policies(Scope='Local')['Policies'] if policy['PolicyName'] == POLICY_NAME)
    iam.detach_role_policy(RoleName = ROLE_NAME, PolicyArn = POLICY_ARN)
    iam.detach_role_policy(RoleName = ROLE_NAME, PolicyArn = 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole')
    print('Deleting role', ROLE_NAME)
    iam.delete_role(RoleName = ROLE_NAME)

if 'delete-policy' in sys.argv or 'delete-everything' in sys.argv:
    print('Deleting policy', POLICY_NAME)
    POLICY_ARN = next(policy['Arn'] for policy in iam.list_policies(Scope='Local')['Policies'] if policy['PolicyName'] == POLICY_NAME)
    iam.delete_policy(PolicyArn = POLICY_ARN)

if 'delete-region' in sys.argv or 'delete-everything' in sys.argv:
    exit(0)

if 'status' in sys.argv:
    try:
       next(policy['Arn'] for policy in iam.list_policies(Scope='Local')['Policies'] if policy['PolicyName'] == POLICY_NAME)
       print('Policy', POLICY_NAME, 'exists')
    except StopIteration:
       print('Policy', POLICY_NAME, 'does not exist')
    try:
        ROLE = iam.get_role(RoleName = ROLE_NAME)['Role']['Arn']
        print('Role', ROLE_NAME, 'exists')
    except iam.exceptions.NoSuchEntityException:
        print('Role', ROLE_NAME, 'does not exist')
    try:
        lambda_function = l.get_function(FunctionName=FUNCTION_NAME)['Configuration']
        print('Lambda function', FUNCTION_NAME, 'exists')
    except l.exceptions.ResourceNotFoundException:
        print('Lambda function', FUNCTION_NAME, 'does not exist')
    try:
        URL = next(item['ApiEndpoint'] for item in apigw.get_apis()['Items'] if item['Name'] == API_NAME)
        print('API', API_NAME, 'exists')
        print('URL', URL + '/login')
    except StopIteration:
        print('API', API_NAME, 'does not exist')
    exit(0)

try:
    POLICY_ARN = next(policy['Arn'] for policy in iam.list_policies(Scope='Local')['Policies'] if policy['PolicyName'] == POLICY_NAME)
except StopIteration:
    print('Creating policy', POLICY_NAME)
    POLICY_ARN = iam.create_policy(PolicyName = POLICY_NAME, PolicyDocument = json.dumps(role_policy))['Policy']['Arn']

try:
    ROLE = iam.get_role(RoleName = ROLE_NAME)['Role']['Arn']
except iam.exceptions.NoSuchEntityException:
    print('Creating role', ROLE_NAME)
    ROLE = iam.create_role(RoleName = ROLE_NAME, AssumeRolePolicyDocument = json.dumps(assume_role_policy))['Role']['Arn']

role_policies = iam.list_attached_role_policies(RoleName = ROLE_NAME)
role_policy_arns = [p['PolicyArn'] for p in role_policies['AttachedPolicies']]

LAMBDA_POLICY_ARN = 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'

if POLICY_ARN not in role_policy_arns:
   print('Attaching policy', POLICY_ARN, "to role", ROLE_NAME)
   iam.attach_role_policy(RoleName = ROLE_NAME, PolicyArn = POLICY_ARN)
if LAMBDA_POLICY_ARN not in role_policy_arns:
   print('Attaching policy', LAMBDA_POLICY_ARN, "to role", ROLE_NAME)
   iam.attach_role_policy(RoleName = ROLE_NAME, PolicyArn = LAMBDA_POLICY_ARN)

with open(DEPLOYMENT_PACKAGE, 'rb') as f:
    zipfile = f.read()

try:
    lambda_function = l.get_function(FunctionName=FUNCTION_NAME)['Configuration']
    current_AWS_sha256 = lambda_function['CodeSha256']
    m = hashlib.sha256()
    m.update(zipfile)
    local_code_sha256 = base64.b64encode(m.digest()).decode()
    if current_AWS_sha256 != local_code_sha256:
        print('Updating function', FUNCTION_NAME)
        l.update_function_code(FunctionName = FUNCTION_NAME, ZipFile=zipfile)
    FUNCTION_ARN = lambda_function['FunctionArn']
except l.exceptions.ResourceNotFoundException:
    print('Creating function', FUNCTION_NAME)
    # Sometimes this fails right after creating the role with the message:
    #    "The role defined for the function cannot be assumed by Lambda."
    # Seems to be a race condition with AWS; just re-run the script
    FUNCTION_ARN = l.create_function(FunctionName=FUNCTION_NAME, Role=ROLE, Runtime='python3.9',
                                     PackageType='Zip', Code={'ZipFile': zipfile},
                                     Environment=environment,
                                     Handler='lambda_function.lambda_handler', Timeout=60)['FunctionArn']

current_AWS_environment = l.get_function_configuration(FunctionName=FUNCTION_NAME)['Environment']
if current_AWS_environment != environment:
    print(f'updating {FUNCTION_NAME} function environment')
    l.update_function_configuration(FunctionName = FUNCTION_NAME, Environment = environment)

try:
    URL = next(item['ApiEndpoint'] for item in apigw.get_apis()['Items'] if item['Name'] == API_NAME)
except StopIteration:
    print('Creating API', API_NAME)
    API = apigw.create_api(Name=API_NAME, ProtocolType='HTTP', Target=FUNCTION_ARN, RouteKey='ANY /login')
    API_ID = API['ApiId']
    URL = API['ApiEndpoint']

    REGION = boto3.DEFAULT_SESSION.region_name
    STATEMENT_ID = 'apigateway-get-{}'.format(REGION)
    # From: https://docs.aws.amazon.com/apigateway/latest/developerguide/arn-format-reference.html
    # Syntax: arn:partition:execute-api:region:account-id:api-id/stage/http-method/resource-path
    SOURCE_ARN = "arn:aws:execute-api:{}:{}:{}/*/*/login".format(REGION, ACCOUNT, API_ID)
    l.add_permission(FunctionName=FUNCTION_NAME, StatementId=STATEMENT_ID, Action='lambda:InvokeFunction',
        Principal='apigateway.amazonaws.com', SourceArn=SOURCE_ARN)

print('URL', URL + '/login')

# Update a SQLite3 database used by bbb-mklogin to obtain the API gateway's url

conn = sqlite3.connect(SQLITE3_DATABASE)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS servers (name text NOT NULL PRIMARY KEY, url text);")
for server in CONFIG.keys():
    c.execute("INSERT INTO servers (name, url) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET url = excluded.url",
              (server, URL + '/login'))
conn.commit()

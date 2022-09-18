#!/usr/bin/env python3
#
# Use AWS boto3 library to install a lambda function to autostart an instance

import os
import sys
import boto3
import json

if 'AWS_PROFILE' not in os.environ:
    print('Specify an AWS profile name in the AWS_PROFILE environment variable')
    exit()

CONFIG = {
    'ts2l': {
        'fqdn': 'ts2lclassroom.org',
        'instances': ['i-037fed505747bcc6c'],
        'keys': ['ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDT6kS1/ZnYXOM5QTDu4RY0mGaVWrz53LpjW9stK+E73JUFQh+FNGUWObab0m+TJzOpaAPMFVor1GaN/RdMPgNW537mGBH7H2LnQhSv3A3Sw5GvxZw11sy4ek6T2m2NVsemSvMgeUi/nPkt7vhgZdjktMkRS0MoErv0FsaZaqHTfnXqZ2saOqIy9FWusWZMQe60hvYAmAPZFB7AUE1Yj6ZyvcI+lZeHCtylvQUJrX1zwvhYPuwMd25ZCWAHLyQfTxpuS5Wv2aPDTwIsl9bSdbqv1myvEnkG/nGKrP1fH47GwnqfQZCl4Kzht/DaH1Q7uwIFdP4hpjce1kphJZBPexDJ ubuntu@ts2lclassroom']
    },
    'collaborate': {
        'fqdn': 'collaborate.freesoft.org',
        'instances': ['i-0d7982250b4e835d7'],
        'keys': ['ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCzuN81Hcxd5wpfT8JFzhFXG0JoyOpLAOGl6r0bb4iTt86VJMfvByJorKHVWi/Wp1qRqzAAeAnlSKRTm7CeIy744Y1/iaWQwDMkS+Sjwhib104sqM8EIFVVeiorvwPa8GbpdgxS6H6s5zO4mlnW5MdiV67jlyd0xWc3jDWCqwGLJBgYrJEuztQ5hlLDfliDSs8ZpSijgkROII2yORuU+YuVkHgFcmRDXnIKq7iL5xKW89KGSU8yOi6v1iW9xccs0m5hB35B3zX8Kha25dhBpVXrLlvP8Xf2y8MYIoYVaYurLLqSVmRoGMXOnaXxw3iX9ERMvuhj0PIPNPOK7ZJvN3en baccala@samsung']
    },
}

assert len(json.dumps(CONFIG)) <= 4096

environment = { "Variables" : {"CONFIG" : json.dumps(CONFIG)} }

sts = boto3.client('sts')
apigw = boto3.client('apigatewayv2')
iam = boto3.client('iam')
l = boto3.client('lambda')

ACCOUNT = sts.get_caller_identity()['Account']
print('Account', ACCOUNT)

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

    #print(ROUTE_ID)
    #apigw.delete_route(ApiId=API_ID, RouteId=ROUTE_ID)
    #apigw.delete_integration(ApiId=API_ID, IntegrationId=INTEGRATION_ID)
    print('Deleting API', API_ID)
    apigw.delete_api(ApiId=API_ID)

    #aws lambda delete-function --function-name login
    #POLICY_ARN=$(aws iam list-policies --scope=Local --output=json | jq -r '.Policies[] | select (.PolicyName == "login").Arn')
    #aws iam detach-role-policy --role-name login --policy-arn $POLICY_ARN
    #aws iam delete-policy --policy-arn $POLICY_ARN

if len(sys.argv) > 1 and sys.argv[1] == 'add-global':
    pass
    #aws iam create-policy --policy-name login --policy-document "$(cat login-role-policy)"

    # this appears to be global to all AWS regions
    #POLICY_ARN=$(aws iam list-policies --scope=Local --output=json | jq -r '.Policies[] | select (.PolicyName == "login").Arn')

    #aws iam attach-role-policy --role-name login --policy-arn $POLICY_ARN
    #aws iam attach-role-policy --role-name login --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

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

try:
    URL = next(item['ApiEndpoint'] for item in apigw.get_apis()['Items'] if item['Name'] == 'login')
    with open('aws-login/my-deployment-package.zip', 'rb') as f:
        zipfile = f.read()
    l.update_function_code(FunctionName = 'login', ZipFile=zipfile)
    l.update_function_configuration(FunctionName = 'login', Environment = environment)

except StopIteration:
    with open('aws-login/my-deployment-package.zip', 'rb') as f:
        zipfile = f.read()
    FUNCTION_ARN = l.create_function(FunctionName='login', Role=ROLE, Runtime='python3.9',
                                     PackageType='Zip', Code={'ZipFile': zipfile},
                                     Environment=environment,
                                     Handler='lambda_function.lambda_handler', Timeout=60)['FunctionArn']
    #print(FUNCTION_ARN)

    API = apigw.create_api(Name='login', ProtocolType='HTTP', Target=FUNCTION_ARN, RouteKey='ANY /login')
    API_ID = API['ApiId']
    URL = API['ApiEndpoint']

    REGION = boto3.DEFAULT_SESSION.region_name
    STATEMENT_ID = 'apigateway-get-{}'.format(REGION)
    SOURCE_ARN = "arn:aws:execute-api:{}:{}:{}/*/*/login".format(REGION, ACCOUNT, API_ID)
    l.add_permission(FunctionName='login', StatementId=STATEMENT_ID, Action='lambda:InvokeFunction',
        Principal='apigateway.amazonaws.com', SourceArn=SOURCE_ARN)

print('URL', URL + '/login')

#!/bin/bash
#
# Use AWS command line to install a lambda function to autostart an instance

if [[ -z "${AWS_PROFILE}" ]]; then
    echo 'Specify an AWS profile name in the AWS_PROFILE environment variable'
    exit 1
fi

if [[ $1 == 'delete' ]]; then
    API_IDS=$(aws apigatewayv2 get-apis --output=json | jq -r '.Items[] | select(.Name=="login").ApiId')
    for API_ID in $API_IDS; do
       ROUTE_ID=$(aws apigatewayv2 get-routes --api-id $API_ID --output=json | jq -r '.Items[0].RouteId')
       INTEGRATION_ID=$(aws apigatewayv2 get-integrations --api-id $API_ID --output=json | jq -r '.Items[0].IntegrationId')
       aws apigatewayv2 delete-route --api-id $API_ID --route-id $ROUTE_ID
       # delete-integration always gives an error that some route still exists
       aws apigatewayv2 delete-integration --api-id $API_ID --integration-id $INTEGRATION_ID
       aws apigatewayv2 delete-api --api-id $API_ID
    done
    aws lambda delete-function --function-name login
    POLICY_ARN=$(aws iam list-policies --scope=Local --output=json | jq -r '.Policies[] | select (.PolicyName == "login").Arn')
    aws iam detach-role-policy --role-name login --policy-arn $POLICY_ARN
    aws iam delete-policy --policy-arn $POLICY_ARN
    # Can't delete role because it's attached to an instance
    # aws iam delete-role --role-name login
    exit
fi

if [[ $1 == 'add-global' ]]; then

    # The IAM policies and roles are global to all AWS regions

    # THIS DOESN'T WORK:
    #aws iam create-role --role-name login --assume-role-policy-document "$(cat lambda-role-policy)"

    aws iam create-policy --policy-name login --policy-document "$(cat login-role-policy)"

    # this appears to be global to all AWS regions
    POLICY_ARN=$(aws iam list-policies --scope=Local --output=json | jq -r '.Policies[] | select (.PolicyName == "login").Arn')

    aws iam attach-role-policy --role-name login --policy-arn $POLICY_ARN
    aws iam attach-role-policy --role-name login --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
fi

UPDATE_FUNCTION=no

if [[ ! -r aws-login/my-deployment-package.zip ]]; then

    mkdir -p aws-login
    cd aws-login

    pip3 install --target package requests
    # Need version 1.7.1 because newer ones require an 'algorithms' argument to jwt.decode() even if verify=False
    pip3 install --target package pyjwt==1.7.1
    pip3 install --target package serialization
    # (last command will show "ERROR: launchpadlib 1.10.13 requires testresources, which is not installed.")
    # cryptography uses a binary shared object, and can be quite tricky to get working on lambda
    # See https://aws.amazon.com/premiumsupport/knowledge-center/lambda-python-package-compatible/
    pip3 install --target package --platform manylinux2014_x86_64 --python-version=3.9 --implementation cp --only-binary=:all: --upgrade cryptography
    pip3 install --target package dnspython
    unzip -d package cffi-1.15.0-cp39-cp39-manylinux_2_12_x86_64.manylinux2010_x86_64.whl

    cd package; zip -r ../my-deployment-package.zip .; cd ..
    zip -g -j my-deployment-package.zip ../lambda_function.py

    cd ..

    UPDATE_FUNCTION=yes
fi

# If deployment package has already been built, but python code has been updated, update the deployment package

if [[ lambda_function.py -nt aws-login/my-deployment-package.zip ]]; then
    cd aws-login
    echo zip -g -j my-deployment-package.zip ../lambda_function.py
    zip -g -j my-deployment-package.zip ../lambda_function.py
    cd ..
    UPDATE_FUNCTION=yes
fi

URL=$(aws apigatewayv2 get-apis --output=json | jq -r '.Items[] | select(.Name == "login") | .ApiEndpoint')

if [[ -z $URL ]]; then

    # A lambda function is local to an AWS region

    # I also increased the time limit on the lambda process to 60 sec.  This much time is needed because, when
    # called from 'waitpage', we wait for the collaborate server to start and register its DNS, which can be slow.

    aws lambda create-function --function-name login --role $(aws iam list-roles --output=json | jq -r '.Roles[] | select (.RoleName=="login").Arn') --runtime=python3.9 --zip-file=fileb://aws-login/my-deployment-package.zip --handler=lambda_function.lambda_handler --timeout=60

    # local to an AWS region
    FUNCTION_ARN=$(aws lambda list-functions --output=json | jq -r '.Functions[] | select(.FunctionName == "login").FunctionArn')

    aws apigatewayv2 create-api --name login --protocol-type HTTP --target $FUNCTION_ARN --route-key 'ANY /login'

    API_ID=$(aws apigatewayv2 get-apis --output=json | jq -r '.Items[] | select(.Name=="login").ApiId')

    # aws apigatewayv2 create-integration --api-id=$API_ID --integration-type=AWS_PROXY --integration-method=POST --integration-uri=$FUNCTION_ARN --payload-format-version=2.0

    # INTEGRATION_ID=$(aws apigatewayv2 get-integrations --api-id $API_ID --output=json | jq -r '.Items[0].IntegrationId')
    INTEGRATION_URI=$(aws apigatewayv2 get-integrations --api-id $API_ID --output=json | jq -r '.Items[0].IntegrationUri')

    # aws apigatewayv2 create-route --api-id=$API_ID --route-key='ANY /login' --target=integrations/$INTEGRATION_ID

    ACCOUNT_ID=$(aws sts get-caller-identity --output=json | jq -r .Account)

    aws lambda add-permission --function-name login --statement-id apigateway-get --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:us-east-1:$ACCOUNT_ID:$API_ID/*/*/login"

    # This adds another permission for us-west-1:

    aws lambda add-permission --function-name login --statement-id apigateway-get-us-west-1 --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:us-west-1:$ACCOUNT_ID:$API_ID/*/*/login"

    #aws lambda add-permission --function-name login --statement-id apigateway-get --action lambda:InvokeFunction \
    #    --principal apigateway.amazonaws.com --source-arn $INTEGRATION_URI

    URL=$(aws apigatewayv2 get-apis --output=json | jq -r '.Items[] | select(.Name == "login") | .ApiEndpoint')
fi

echo $URL

# Can't do both this and the setting the environment (below) back-to-back because "an update is in progress"

if [[ $UPDATE_FUNCTION = yes ]]; then
    aws lambda update-function-code --function-name login --zip-file fileb://aws-login/my-deployment-package.zip
fi

# Basically, this:  (but the quoting in bash is a bear)
# aws lambda update-function-configuration --function-name login --environment "Variables={BUCKET=my-bucket,KEY=file.txt}"

#python3 <<EOF
echo <<EOF
import json

environment = {
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

assert len(json.dumps(environment)) <= 4096

import boto3
l = boto3.client('lambda')
print(l.update_function_configuration(FunctionName = 'login',
                                      Environment = { "Variables" : {"CONFIG" : json.dumps(environment)}}))

EOF

# echo aws lambda update-function-configuration --function-name login --environment $QUOTED_ENVIRONMENT

# aws lambda get-function-configuration --function-name login

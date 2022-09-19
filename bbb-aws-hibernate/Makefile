
aws: aws-login/my-deployment-package.zip
	./install-lambda.py

logs:
	awslogs get /aws/lambda/login

# depends on /dev/null so it will only get built if it doesn't already exist
aws-login/my-deployment-package.zip:: /dev/null
	mkdir -p aws-login

	cd aws-login; pip3 install --target package requests
	# Need version 1.7.1 because newer ones require an 'algorithms' argument to jwt.decode() even if verify=False
	cd aws-login; pip3 install --target package pyjwt==1.7.1
	cd aws-login; pip3 install --target package serialization
	# (last command will show "ERROR: launchpadlib 1.10.13 requires testresources, which is not installed.")
	# cryptography uses a binary shared object, and can be quite tricky to get working on lambda
	# See https://aws.amazon.com/premiumsupport/knowledge-center/lambda-python-package-compatible/
	cd aws-login; pip3 install --target package --platform manylinux2014_x86_64 --python-version=3.9 --implementation cp --only-binary=:all: --upgrade cryptography
	cd aws-login; pip3 install --target package dnspython

	cd aws-login/package; zip -r ../my-deployment-package.zip .

aws-login/my-deployment-package.zip:: lambda_function.py
	zip -g -j aws-login/my-deployment-package.zip lambda_function.py

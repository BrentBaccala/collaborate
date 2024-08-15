
aws: build/deployment-package.zip
	./install-lambda.py

logs:
	awslogs get /aws/lambda/login

build/deployment-package.zip: lambda_function.py
	mkdir -p build

	pip3 install --target build/package requests
	# Need version 1.7.1 because newer ones require an 'algorithms' argument to jwt.decode() even if verify=False
	pip3 install --target build/package pyjwt==1.7.1
	pip3 install --target build/package serialization
	# (last command will show "ERROR: launchpadlib 1.10.13 requires testresources, which is not installed.")
	# cryptography uses a binary shared object, and can be quite tricky to get working on lambda
	# See https://aws.amazon.com/premiumsupport/knowledge-center/lambda-python-package-compatible/
	pip3 install --target build/package --platform manylinux2014_x86_64 --python-version=3.9 --implementation cp --only-binary=:all: --upgrade cryptography
	pip3 install --target build/package dnspython

	cd build/package; zip -r ../deployment-package.zip .

	zip -g -j build/deployment-package.zip lambda_function.py

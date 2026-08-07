#!/bin/bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
pip install --upgrade setuptools
python -c "import setuptools; import pkg_resources; print('pkg_resources found')"

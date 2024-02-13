#!/bin/bash
set -ex
# OVERVIEW
# This script stops a SageMaker notebook once it's idle for more than 1 hour (default time)
# You can change the idle time for stop using the environment variable below.
# If you want the notebook the stop only if no browsers are open, remove the --ignore-connections flag
#
# Note that this script will fail if either condition is not met
#   1. Ensure the Notebook Instance has internet connectivity to fetch the example config
#   2. Ensure the Notebook Instance execution role permissions to SageMaker:StopNotebookInstance to stop the notebook 
#       and SageMaker:DescribeNotebookInstance to describe the notebook.
#
# PARAMETERS 
IDLE_TIME=60  ### in seconds. Change this 
echo "Fetching the autostop script"
aws s3 cp <INSERT_S3_URI_HERE> autostop.py


echo "Detecting Python install with boto3 install"
sudo apt-get update -y
sudo apt-get install -y vim 
sudo sh -c 'printf "#!/bin/sh\nexit 0" > /usr/sbin/policy-rc.d'
## required as part of https://stackoverflow.com/questions/46247032/how-to-solve-invoke-rc-d-policy-rc-d-denied-execution-of-start-when-building
sudo apt-get install -y cron
sudo sudo service cron start
# Find which install has boto3 and use that to run the cron command. So will use default when available
# Redirect stderr as it is unneeded
CONDA_PYTHON_DIR=$(source /opt/conda/bin/activate base && which python)
if $CONDA_PYTHON_DIR -c "import boto3" 2>/dev/null; then
    PYTHON_DIR=$CONDA_PYTHON_DIR
elif /usr/bin/python -c "import boto3" 2>/dev/null; then
    PYTHON_DIR='/usr/bin/python'
else
    # If no boto3 just quit because the script won't work
    echo "No boto3 found in Python or Python3. Exiting..."
    exit 1
fi
echo "Found boto3 at $PYTHON_DIR"

echo "Starting the SageMaker autostop script in cron"
echo "*/5 * * * * export AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI; $PYTHON_DIR $PWD/autostop.py --time $IDLE_TIME --region $AWS_DEFAULT_REGION --ignore-connections >> /home/sagemaker-user/autoshutdown.log" | crontab 

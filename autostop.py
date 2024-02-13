#     Copyright 2023 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#     Licensed under the Apache License, Version 2.0 (the "License").
#     You may not use this file except in compliance with the License.
#     A copy of the License is located at
#
#         https://aws.amazon.com/apache-2-0/
#
#     or in the "license" file accompanying this file. This file is distributed
#     on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
#     express or implied. See the License for the specific language governing
#     permissions and limitations under the License.

import requests
from datetime import datetime
import getopt, sys
import time as t
import urllib3
import boto3
import json
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Usage
usageInfo = """Usage:
This scripts checks if a notebook is idle for X seconds if it does, it'll stop the notebook:
python autostop.py --time <time_in_seconds> [--port <jupyter_port>] [--ignore-connections]
Type "python autostop.py -h" for available options.
"""
# Help info
helpInfo = """-t, --time
    Auto stop time in seconds
-p, --port
    jupyter port
-c --ignore-connections
    Stop notebook once idle, ignore connected users
-h, --help
    Help information
"""

# Read in command-line parameters
idle = True
port = '8888'
ignore_connections = False
try:
    opts, args = getopt.getopt(sys.argv[1:], "ht:p:c", ["help","time=","port=","ignore-connections", "region="]) # Add "region=" to the list of options
    if len(opts) == 0:
        raise getopt.GetoptError("No input parameters!")
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print(helpInfo)
            exit(0)
        if opt in ("-t", "--time"):
            time = int(arg)
        if opt in ("-p", "--port"):
            port = str(arg)
        if opt in ("-c", "--ignore-connections"):
            ignore_connections = True
        if opt in ("--region"):  # Handle the new "region" option
            region = str(arg)
except getopt.GetoptError:
    print(usageInfo)
    exit(1)

# Missing configuration notification
missingConfiguration = False
if not time:
    print("Missing '-t' or '--time'")
    missingConfiguration = True
if missingConfiguration:
    exit(2)


def is_idle(last_activity):
    last_activity = datetime.strptime(last_activity,"%Y-%m-%dT%H:%M:%S.%fz")
    if (datetime.now() - last_activity).total_seconds() > time:
        # print('Space is idle. Last activity time = ', last_activity)
        return True
    else:
        print('Space is not idle. Last activity time = ', last_activity)
        return False
        
def get_studio_app_details():
    metadata = '/opt/ml/metadata/resource-metadata.json'
    with open(metadata, 'r') as metdata:
        _conf = json.load(metdata)
    return _conf["DomainId"], _conf["SpaceName"],_conf["AppType"],_conf["ResourceName"]
    
def get_notebook_name():
    log_path = '/opt/ml/metadata/resource-metadata.json'
    with open(log_path, 'r') as logs:
        _logs = json.load(logs)
    return _logs['ResourceName']

def get_last_modified_time(path):
    return os.path.getmtime(path)
    
## path for new Jupyter Lab 
prefix="/jupyterlab/default"

# This is hitting Jupyter's sessions API: https://github.com/jupyter/jupyter/wiki/Jupyter-Notebook-Server-API#Sessions-API
nb_sessions = requests.get('http://default:'+port+prefix+'/api/sessions', verify=False).json()
terminals = requests.get('http://default:'+port+prefix+'/api/terminals', verify=False).json()
files = requests.get('http://default:'+port+prefix+'/api/contents', verify=False).json()
DomainId, SpaceName, AppType, AppName = get_studio_app_details()

if len(nb_sessions) > 0:
    for notebook in nb_sessions:
        # Idleness is defined by Jupyter
        # https://github.com/jupyter/notebook/issues/4634
        if notebook['kernel']['execution_state'] == 'idle':
            if not ignore_connections:
                if notebook['kernel']['connections'] == 0:
                    if not is_idle(notebook['kernel']['last_activity']):
                        idle = False
                else:
                    idle = False
                    print(f'{AppType} idle state set as {idle} because no kernel has been detected.')
            else:
                if not is_idle(notebook['kernel']['last_activity']):
                    idle = False
                    print(f'{AppType} idle state set as {idle} since kernel connections are ignored.')
        else:
            print(f'{AppType} is not idle:', notebook['kernel']['execution_state'])
            idle = False

if idle and len(terminals) > 0:
    print("No active notebook sessions, checking terminal sessions")
    for terminal in terminals:
        if not is_idle(terminal['last_activity']):
            idle = False
            print(f"A terminal session is still active, setting idle state to {idle}")
elif idle:
    print("No active notebook & terminal sessions detected, checking Last Modified status of files")
    directory = os.getcwd()
    for root, dirs, files in os.walk(directory):
        for file in files:
            if '/.' not in root:
                path = os.path.join(root, file)
                mod_time = t.gmtime(get_last_modified_time(path))
                if not is_idle(t.strftime('%Y-%m-%dT%H:%M:%S.000z', mod_time)) and file != 'autoshutdown.log':
                    idle = False
                    print(f'{AppType} idle state set as {idle} since a file has been modified within time limit.')
                    break

if idle:
    print('Initiating Shutdown')
    client = boto3.client('sagemaker',region_name=region)
    print(DomainId,AppType,AppName,SpaceName)
    response = client.delete_app(
        DomainId=DomainId,
        SpaceName=SpaceName,
        AppType=AppType,
        AppName=AppName,
    )
    print(response)
    print(f'{AppType}: {SpaceName}  Shutdown')
else:
    print(f'{AppType}: {SpaceName} not idle. Pass.')
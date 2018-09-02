#!/usr/bin/env python3
from flask import Flask
from flask import request, session
import urllib.request
import time 
import yaml
from uuid import uuid4

# Changelog since commit #6c4963d:
# 1. Email notifcations temporarily removed.
# 2. Fixed handling of multiple alerting probes
# 3. Code cleanup + more OOD

# Load config file
with open('alerter_settings.yaml') as f:
    try:
        conf = yaml.safe_load(f)
    except:
        raise IOError('Fatal: Could not load the configuration file')

# Parse settings
try:
    webhook_notify = conf['settings']['publisher']['mattermost']['enabled']
    email_notify = conf['settings']['publisher']['email']['enabled']
    hook_url = conf['settings']['publisher']['mattermost']['hook_url']
    smtp_server = conf['settings']['publisher']['email']['smtp_server']
    sender_address = conf['settings']['publisher']['email']['sender_address']
    receiver_address = conf['settings']['publisher']['email']['receiver_address']
    subject = conf['settings']['publisher']['email']['subject']
    webdav_path = conf['settings']['general']['webdav_path']
    grafana_webdav = conf['settings']['general']['grafana_webdav']
    ext_charturl = conf['settings']['general']['ext_charturl']
    grafana_testurl = conf['settings']['general']['grafana_testurl']
    verbose = conf['settings']['general']['verbose']
except:
    raise KeyError('Fatal: Could not parse the configuration file')

# icmp deadline
icmp_deadline = 100

# Class used to create object for incoming alerts 
class Alert:
    def __init__(self, data, probes='not-available'):
        self.created = time.strftime("%Y-%m-%d %H:%M")
        self.id = uuid4()
        self.data = data
        self.value = None
        for key, value in data.items():
            setattr(self, key, value)
        if self.evalMatches:
            self.alertdetails = self.evalMatches
            self.probes = {}
            for index in self.alertdetails:
                self.probes[index['metric']] = index['value']
        else:
            self.probes = probes

    def prettyvalue(self,extra_text=""):
        returned_values = []
        for index in self.alertdetails:
            prettyvalue = float(format(index['value'], '.2f'))
            returned_values.append(str(prettyvalue) + extra_text)
        return(', '.join(returned_values))

    def listprobes(self,o_format='list'):
        if 'pretty' in o_format:
            return((', '.join(self.probes.keys())))
        elif 'list' in o_format:
            return(list(self.probes.keys()))

def load_graph(url):
    urllib.request.urlretrieve(url, 'test.png')
    return

def fetch_image(url, urldir):
    """ Fetch string after delimiter (webdir/) """
    return url.partition(urldir)[2]

if webhook_notify:
    import requests

app = Flask(__name__)
app.secret_key = "something-from-os.urandom(24)"
 
@app.route('/alert', methods = ['POST'])
def postJsonHandler():
    print ('Is json? ',request.is_json) if verbose else None
    try:
        d = request.get_json()
    except:
        raise('Incorrect JSON provided')

#   Create object from json data
    alert = Alert(d)
#    alerting_probe = d['evalMatches'][0]['metric']
    chart_url = alert.imageUrl
    print(chart_url) if verbose else None
    print (d) if verbose else None
    print('Recieved alert state:',alert.state) if verbose else None

# Parse settings from message
# Script should still function without message settings.
    try:
        alert_settings = alert.message
        message = True
   
    except (AttributeError, KeyError) as e: 
        message = False
        print('Warning: No message key was detected in the alert:', e)
    
    if message:
        try:
            if isinstance(alert_settings,str):
                alert_settings = eval(alert.message)
            else:
                alert_settings = alert.message
            icmp_size = alert_settings['icmp_size'] if 'icmp_size' in alert_settings else None
            icmp_interval = alert_settings['icmp_interval'] if 'icmp_interval' in alert_settings else None
        except NameError:
            message = False
            print('Warning: alert settings (grafana message field) does not contain any known variables')

    print(chart_url) if verbose else None
    print (d) if verbose else None
    print('Recieved alert state:',alert.state) if verbose else None

# Check if alert is a grafana test
    if 'Test notification' in alert.ruleName:
        test_alert = True
    else:
        test_alert = False

# If alert state is 'No data' or 'OK' just drop them unless we're just testing
    if alert.state in ('ok', 'no_data'):
        print('Dropped request with state:', alert.state)
        return 'Dropped request due to state'

    elif 'alerting' in alert.state:
        if test_alert: # Use dummy data if testing
            alert.probes = 'test_notification'
            alert.value = 'test_value'
            alert_hvalue = 'ms'
            print(alert.probes, alert.prettyvalue()) if verbose else None

        else: # Parse probe name and value

            # Add some claryfing text to the values
            if 'Max RTT' in alert.title:
                alert_hvalue = alert.prettyvalue('ms RTT (spike)')

            elif 'Average RTT' in alert.title:
                alert_hvalue = alert.prettyvalue('ms RTT (avg)')
                        
            elif 'Loss' in alert.title:
            # Check interval time from message field and use it to measure outage time
            # Fetches the highest value if multiple
                if icmp_deadline == 100 and message:
                    outage_s = icmp_interval * max(alert.prettyvalue())
                    alert_hvalue = alert.prettyvalue('% packetloss (~{} seconds)').format(int(outage_s))
                else:
                    alert_hvalue = alert.prettyvalue('% packetloss')

    else:
        print('Dropped request with state:', alert.state)
        return 'Dropped request due to state'

    if webhook_notify:

        if grafana_testurl in chart_url:
            final_image = chart_url

        else:
            chart_png = fetch_image(chart_url,'/webdav/')
            final_image = ext_charturl + chart_png
        if not chart_url:
            chart_url = '<no image available>'
        
# Create the POST
        if 'alerting' in alert.state:
            alert_text = \
'Alert from chprobe at {}. Title: {} \n\
Alert state: {} \n\
Probe(s): {} \n\
Alert value: {} \n\
Check Grafana for further info: {} \n'.format(alert.created, alert.title, alert.state, alert.listprobes('pretty'), alert_hvalue, alert.ruleUrl)

        else:
            alert_text = \
'Alert from chprobe at {}. Title: {} \n\
Alert state: {} \n\
Check Grafana for further info: {} \n'.format(alert.created, alert.title, alert.state, alert.ruleUrl)
        markdown_newline = '  '
        dict_in = dict()
        dict_in['text'] = alert_text + '![alertgraph]' + '(' + final_image + ')'
        json_input = dict_in

# Send the POST
        r = requests.post(hook_url, json=json_input)
        if verbose:
            print('response code: ', r.status_code)
            print('response text: ', r.text)
            print('What we sent: ', json_input)
    return 'JSON posted'
 
app.run(host='127.0.0.1', port= 8092, debug=False)

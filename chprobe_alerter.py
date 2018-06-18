#!/usr/bin/env python3
# v0.2
from flask import Flask
from flask import request, session
import urllib.request
import time 

# TODO
# Make class for alert_ vars instead
# Issues: Email notify sends multiple attachments
# Handling of multiple probes in evalMatches list.. Currently only takes index 0

verbose = True
email_notify = False
webhook_notify = True

## Settings

# Webhook url and key
hook_url = '<webhook url here>'

# Local path for grafanas upload dir
webdav_path = '<upload path here>'

# External path for grafanas (included in the POST)
grafana_webdav = '<external path here>'

# External url where the graphs are stored when pointing to them and not attaching them
ext_charturl = '<chart url here>'

# Grafana testing url
grafana_testurl = 'http://grafana.org/assets/img/blog/mixed_styles.png'

# SMTP server
smtpserver = '127.0.0.1'

def load_graph(url):
    urllib.request.urlretrieve(url, 'test.png')
#   r = urllib.request.urlopen(url)
#   img = r.read()
#   with open('img.png', 'wb') as ofile:
#       ofile.write(img)
#   return img  # img never gets defined when function is called in the decorator...
    return

def fetch_image(url, urldir):
    """ Fetch string after delimiter (webdir/) """
    return url.partition(urldir)[2]

if email_notify:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    strFrom = 'somesender@somedomain.dom'
    strTo = 'somerecipient@somedomain.com'
    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = 'test message'
    msgRoot['From'] = strFrom
    msgRoot['To'] = strTo

elif webhook_notify:
    import requests
# Create request and send it to MM webhook...


app = Flask(__name__)
 
@app.route('/alert', methods = ['POST'])
def postJsonHandler():
    print ('Is json? ',request.is_json) if verbose else None
    alert_localtime = time.strftime("%Y-%m-%d %H:%M")
    d = request.get_json()
    rule_url = d['ruleUrl']
#    alerting_probe = d['evalMatches'][0]['metric']
    alert_state = d['state']
    alert_title = d['title']
    alert_rulename = d['ruleName']
    chart_url = d['imageUrl']
    print(chart_url) if verbose else None
    print (d) if verbose else None
    print('Recieved alert state:',alert_state) if verbose else None

# Check if alert is a grafana test
    if 'Test notification' in alert_rulename:
        test_alert = True
    else:
        test_alert = False

# If alert state is 'No data' or 'OK' just drop them unless we're just testing
    if alert_state in ('ok', 'no_data'):
        print('Dropped request with state:', alert_state)
        return 'Dropped request due to state'

    elif 'alerting' in alert_state:
        if test_alert: # Use dummy data if testing
            alert_probe = 'test_notification'
            alert_value = 'test_value'
            alert_hvalue = 'ms'
            print(alert_probe, alert_value) if verbose else None

        else: # Parse probe name and value
            alert_probe = d['evalMatches'][0]['metric']
            alert_value = d['evalMatches'][0]['value']
            print(alert_probe, alert_value) if verbose else None

            # Add some claryfing text to the values
            if 'Max RTT' in alert_title:
                alert_hvalue = str(alert_value) + 'ms RTT (spike)'

            elif 'Average RTT' in alert_title:
                alert_hvalue = str(alert_value) + 'ms RTT (avg)'
                  
            elif 'Loss' in alert_title:
                alert_hvalue = str(alert_value) + '% (packetloss)'

    else:
        print('Dropped request with state:', alert_state)
        return 'Dropped request due to state'

    if email_notify:
# If image url is embedded in alert, parse the filename and open the file directly since it's on this local machine
        if chart_url:

   # For debugging/testing, accept the testalerter img in the same way
            if grafana_testurl in chart_url:

    # ... And DL the image instead of webdav
                urllib.request.urlretrieve(chart_url, 'mixed_styles.png')
                final_image = fetch_image(chart_url,'/blog/')
            
            else:
                chart_png = fetch_image(chart_url,'/webdav/')
                final_image = webdav_path + chart_png
                print(final_image)

# Otherwise skip attaching image in the notifier
# ....
        else:
           print('No image found in POST, so nothing to attach')  

# Create and send the email
        try:
            msgRoot.preamble = 'multi-part message in MIME format.'
            msgAlternative = MIMEMultipart('alternative')
            msgRoot.attach(msgAlternative)
            msgText = MIMEText('alternative plain text message.')
            msgAlternative.attach(msgText)
#            msgText = MIMEText('<b>Alert for a probe <i>HTML</i> text</b> and an image.<br><img src="cid:image1"><br>Nifty!', 'html')
            mail_body = """\
<p>Alert for: """ + alert_title + """<br>
<br>
Alert trigged at: """ + alert_localtime + """.<br>
Alert reason: """ + 'somereason' + """.<br>
<br>
Graph:<br>
<br>
<img src="cid:image1">
</p>
"""
            msgText = MIMEText(mail_body, 'html')
            msgAlternative.attach(msgText)

            fp = open(final_image, 'rb')
            msgImage = MIMEImage(fp.read())
            fp.close()
            msgImage.add_header('Content-ID', '<image1>')
            msgRoot.attach(msgImage)

# Send the email (this example assumes SMTP authentication is required)
            smtp = smtplib.SMTP()
            smtp.connect(smtpserver)
            smtp.sendmail(strFrom, strTo, msgRoot.as_string())
            smtp.quit()
            print ("Successfully sent email")
#        except SMTPException:
        except:
            pass
#            print ("Error: unable to send email")
        finally:
# Empty the body for the next alert
            session.clear()
            print('.')

    elif webhook_notify:

        if grafana_testurl in chart_url:
            final_image = chart_url

        else:
            chart_png = fetch_image(chart_url,'/webdav/')
            final_image = ext_charturl + chart_png
        if not chart_url:
            chart_url = '<no image available>'
        
# Create the POST
        if 'alerting' in alert_state:
            alert_text = \
'Alert from chprobe at {}. Title: {} \n\
Alert state: {} \n\
Probe: {} \n\
Alert value: {} \n\
Check Grafana for further info: {} \n'.format(alert_localtime, alert_title, alert_state, alert_probe, alert_hvalue, rule_url)

        else:
            alert_text = \
'Alert from chprobe at {}. Title: {} \n\
Alert state: {} \n\
Check Grafana for further info: {} \n'.format(alert_localtime, alert_title, alert_state, rule_url)
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
 
app.run(host='127.0.0.1', port= 8091, debug=True)

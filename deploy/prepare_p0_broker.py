"""Prepare ACLs; provision credentials through the loopback EMQX admin API.

No credentials are printed. Existing broker data is never cleared.
"""
import argparse
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit


def required(name):
    value=os.environ.get(name,'')
    if not value or value.lower().startswith(('replace','change_me')):
        raise SystemExit(name+' must be configured')
    return value


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='workspace/runtime/emqx-p0')
    parser.add_argument('--provision',action='store_true')
    args=parser.parse_args()
    worker=os.getenv('DETECTOR_WORKER_ID','detector-1')
    username=required('MQTT_USERNAME')
    backend=required('MQTT_BACKEND_USERNAME')
    if username!=worker or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',worker) or backend!='railway-backend':
        raise SystemExit('Use a worker-bound username and the dedicated railway-backend account')
    for name in ('MQTT_PASSWORD','MQTT_BACKEND_PASSWORD','EMQX_DASHBOARD_PASSWORD'):
        if len(required(name))<24:raise SystemExit(name+' must have at least 24 characters')
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    cookie=required('RAILWAY_EMQX_COOKIE')
    if not re.fullmatch(r'[A-Za-z0-9_-]{24,128}',cookie):
        raise SystemExit('Node cookie must be a random 24-128 character URL-safe value')
    config=(Path(__file__).parent/'emqx/emqx.conf').read_text()
    (output/'base.conf').write_text(config)
    # No secret is stored here. The node secret is passed as EMQX_NODE__COOKIE.
    (output/'base.conf').chmod(0o644)
    acl='\n'.join([
      '{allow, {username, "railway-backend"}, subscribe, ["railway/v3/+/events", "railway/v3/+/status"]}.',
      '{allow, {username, "railway-backend"}, publish, ["railway/v3/+/ack", "railway/v3/+/control"]}.',
      '{allow, {username, "'+worker+'"}, publish, ["railway/v3/'+worker+'/events", "railway/v3/'+worker+'/status"]}.',
      '{allow, {username, "'+worker+'"}, subscribe, ["railway/v3/'+worker+'/ack", "railway/v3/'+worker+'/control"]}.',
      '{deny, all}.',''])
    (output/'acl.conf').write_text(acl)
    if not args.provision:return
    api=os.getenv('EMQX_ADMIN_URL','http://127.0.0.1:18083')
    target=urlsplit(api)
    if target.scheme!='https' and target.hostname not in ('127.0.0.1','localhost','::1'):
        raise SystemExit('Broker admin provisioning requires HTTPS or loopback')
    def call(path,body,token=None,method='POST'):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        query=Request(api+path,json.dumps(body).encode(),headers,method=method)
        with urlopen(query,timeout=5) as result:
            value=result.read()
            return json.loads(value) if value else {}
    token=call('/api/v5/login',{'username':'admin','password':required('EMQX_DASHBOARD_PASSWORD')})['token']
    auth='/api/v5/authentication/'+quote('password_based:built_in_database',safe='')+'/users'
    for user,password in ((username,required('MQTT_PASSWORD')),(backend,required('MQTT_BACKEND_PASSWORD'))):
        try:call(auth,{'user_id':user,'password':password,'is_superuser':False},token)
        except HTTPError as error:
            if error.code not in (409,):raise
            # Rotation is explicit to the named service accounts only.
            call(auth+'/'+quote(user,safe=''),{'password':password,'is_superuser':False},token,'PUT')
    print('Broker authentication and two least-privilege service accounts configured.')


if __name__=='__main__':main()

from __future__ import print_function
import requests
import unirest
import argparse
import json,pwd,os,time,textwrap,sys
from random import randrange
from colorama import init,Fore,Back,Style

init(autoreset=True)
unirest.timeout(100)
cloudControlurl = 'http://localhost:5000/cloudcontrol/api'
get_status_uri = '/status'
get_resource_uri = '/resource/%s'
start_resource_uri = get_resource_uri + '/start'
stop_resource_uri = get_resource_uri + '/stop'
ext_uri = cloudControlurl + '/ext'

def checkConnection(fn):
	def tryrequest(*args,**kwargs):
		try:
			checkcc = requests.get(cloudControlurl)
			fn(*args,**kwargs)
		except requests.exceptions.ConnectionError:
			print("cloudControl server is not running. Please contact DevOps team.")
		except KeyboardInterrupt:
			print("\nInterrupted by user")
		except Exception as e:
			print(type(e))
			print(e)
	return tryrequest

parser = argparse.ArgumentParser(
	prog="cloudcontrol",
	formatter_class=argparse.RawDescriptionHelpFormatter,
	description=textwrap.dedent('''\
	cloudControl Client Tool v2.0.0
	'''))

subparsers = parser.add_subparsers(title='cloudControl commands',help=Style.BRIGHT + '%(prog)s *command* --help for more info' + Style.RESET_ALL,dest='subp_name')
subp_create = subparsers.add_parser('create',help='Create new environment (dev/qa)',formatter_class=argparse.RawTextHelpFormatter)
subp_create.add_argument('create',nargs='?',metavar='ENVIRONMENT_TYPE',help='(dev | qa) ex: %(prog)s dev | %(prog)s qa')
subp_create.add_argument('-f','--filename',nargs='?',
	help=textwrap.dedent('''File location of the custom configuration file (Overrides default config)

~~ Custom configuration file example ~~

web=1, instance_type=c3.large, security_group=mysecgroup, ami_id=ami-34fdfds
nfs
exp
puppet

Type of instances: t2.micro,t2.small,t2.medium,m3.medium,m3.large,m3.xlarge,
                   c4.large,c4.xlarge,c3.large,c3.xlarge,r3.large,i2.xlarge,
                   d2.xlarge

Security groups: publicsecgroup,privatesecgroup
'''))
subp_create.add_argument('-v','--verbose',action='store_true',help="Increase verbosity when creating environment")

subp_destroy = subparsers.add_parser('destroy',help='Destroy existing environment')
subp_destroy.add_argument('destroy',nargs='?',metavar='ENVIRONMENT_NAME',help='(dev | qa) ex: %(prog)s dev01 | %(prog)s qa01')
subp_destroy.add_argument('-v','--verbose',action='store_true',help="Increase verbosity when destroying environment")

subp_update = subparsers.add_parser('update',help='Update existing environment resources')
subp_update.add_argument('update',nargs='?',metavar='ENVIRONMENT_NAME',help='ex: %(prog)s dev01')
subp_update.add_argument('-f','--filename',nargs='?',help='File location of the updated custom configuration file')
subp_update.add_argument('-v','--verbose',action='store_true',help="Increase verbosity when destroying environment")

subp_list = subparsers.add_parser('list',help='List all environment names/list the environment resource if environment name specified')
subp_list.add_argument('resource',nargs='?',metavar='ENVIRONMENT_NAME',help='ex: %(prog)s | %(prog)s dev01')

subp_viewevent = subparsers.add_parser('viewevent',help='Display specific environment previous events')
subp_viewevent.add_argument('event_view',nargs='?',metavar='ENVIRONMENT_NAME',help='ex: %(prog)s dev01')

subp_start = subparsers.add_parser('start',help='To start all resources in an environment if it stopped')
subp_start.add_argument('startenv',nargs='?',metavar='ENVIRONMENT_NAME',help='ex: %(prog)s dev01')

subp_stop = subparsers.add_parser('stop',help='To stop all resources in an environment if it running')
subp_stop.add_argument('stopenv',nargs='?',metavar='ENVIRONMENT_NAME',help='ex: %(prog)s dev01')

subp_ext = subparsers.add_parser('ext',help='cloudControl extension')
subp_extparser = subp_ext.add_subparsers(title='cloudControl extension commands',help='%(prog)s *command* --help/-h for more info',dest='subpext_name')
subpext_list = subp_extparser.add_parser('list',help='List available cloudControl extension scripts')

subpext_run = subp_extparser.add_parser('run',help='To execute the extension script')
subpext_run.add_argument('ext_name',nargs='?',metavar='EXTENSION_NAME',help='ex: %(prog)s my_extension_script')
subpext_run.add_argument('ext_args',nargs=argparse.REMAINDER)

args = parser.parse_args()
username = pwd.getpwuid(os.getuid())[0]
configdata = ''
server_error = False
cursor_on = "\033[?25h"
cursor_off = "\033[?25l"
color_list = ['Fore.'+c for c in dir(Fore) if c.isupper() and c != 'RESET']

@checkConnection
def createNewEnvironment(envtype):
	data = {'envtype':envtype,'configdata':configdata}
	headers = {'Content-type':'application/json'}
	thread = unirest.put(cloudControlurl,headers=headers,params=json.dumps(data),auth=(username,'cc'),
			callback=cdu_response_callback)
	cdu_proceed_next()

@checkConnection
def destroyEnvironment(envname):
	envtodelete = {'envname':envname}
	headers = {'Content-type':'application/json'}
	thread = unirest.delete(cloudControlurl,headers=headers,params=json.dumps(envtodelete),
			auth=(username,'cc'),callback=cdu_response_callback)
	cdu_proceed_next()

@checkConnection
def updateEnvironment(envname):
	data = {'envname':envname,'configdata':configdata}
	headers = {'Content-type':'application/json'}
	thread = unirest.post(cloudControlurl,headers=headers,params=json.dumps(data),auth=(username,'cc'),
			callback=cdu_response_callback)
	cdu_proceed_next()

def cdu_response_callback(response):
	global server_error
	resp_content = response.body
	if 'status' in resp_content:
		print("\n" + Style.BRIGHT + "Environment name:", Fore.MAGENTA + Style.BRIGHT + resp_content['status']['env_name'])
		#print("Status Url: %s" % resp_content['status']['status_url'])
		if args.verbose and args.update:
			displayEnvironmentStatus(resp_content['status']['env_name'])
	else:
		error = resp_content.get('error','Unidentified value')
		print(error)
		server_error = True

def cdu_proceed_next():
	time.sleep(2.5)
	if not server_error:
		displayScriptEvents()
	else:
		sys.exit(1)

def displayScriptEvents():
	resp_content = unirest.get(cloudControlurl+get_status_uri+'/getevnamenpid')
	evname,pid = resp_content.body['result'].split('_')
	sstatus = get_env_scripts_status(evname,pid)
	proceed_events = True
	if 'error' in sstatus:
		print('**error 13')
	else:
		prev_status = sstatus['script_status']
		print(prev_status.rstrip('\n'),end="")
		if 'FAILURE' in prev_status:
			proceed_events = False
		while proceed_events:
			sstatus = get_env_scripts_status(evname,pid)['script_status']
			if sstatus != prev_status and not 'FAILURE' in sstatus:
				cleaned_st = sanitize_scripts_status(sstatus,prev_status)
				if 'Done!' in cleaned_st:
					print(cleaned_st)
					print("\n")
					print(Fore.YELLOW + Style.BRIGHT + "--- SUCCESS ---")
					print("\n")
					break
				else:
					print(cleaned_st,end="")
			elif 'FAILURE' in sstatus:
				print(sanitize_scripts_status(sstatus,prev_status))
				break
			else:
				print('.',end="")
			prev_status = sstatus
			time.sleep(2)

def get_env_scripts_status(envname,pid):
	script_status_url = cloudControlurl+get_status_uri+'/'+envname+'/'+pid
	resp_content = unirest.get(script_status_url)
	return resp_content.body

def sanitize_scripts_status(currst,prevst):
	latest_stat = len(currst) - (len(currst)-len(prevst))
	return currst[latest_stat:]

def getEnvironmentStatus(envname):
	status_url = cloudControlurl+get_status_uri+'/%s' % envname
	resp = requests.get(status_url,auth=(username,'cc'))
	return json.loads(resp.content)

@checkConnection
def getEnvironmentResource(envname):
	res_url = cloudControlurl+get_resource_uri % envname
	resp = requests.get(res_url,auth=(username,'cc'))
	rsp_ctn = json.loads(resp.content)
	displayEnvironmentResource(rsp_ctn)

@checkConnection
def startEnvironmentResource(envname):
	start_res_url = cloudControlurl+start_resource_uri % envname
	resp = requests.put(start_res_url,auth=(username,'cc'))
	displayStartStopEvents(json.loads(resp.content))

@checkConnection
def stopEnvironmentResource(envname):
	stop_res_url = cloudControlurl+stop_resource_uri % envname
	resp = requests.put(stop_res_url,auth=(username,'cc'))
	displayStartStopEvents(json.loads(resp.content))

@checkConnection
def displayEnvironmentStatus(envname):
	stop_keywords = ['CREATE_COMPLETE','ROLLBACK_COMPLETE','UPDATE_COMPLETE','UPDATE_ROLLBACK_COMPLETE']
	line_width = 20
	ev_val = lambda x : x.ljust(line_width)

	ev_stat = getEnvironmentStatus(envname)
	if 'error' in ev_stat:
		print(ev_stat['error'])
		return
	else:
		stack_events = ev_stat['event_status']
		prev_se_length = len(stack_events)

	startix = len(stack_events)-1
	header = 'Time'.ljust(line_width) + 'Resource Type'.ljust(30) + 'Resource ID'.ljust(line_width) + 'Status'
	print(Fore.BLUE + Style.BRIGHT + header)
	print(Fore.MAGENTA + '='*len(header))

	if any(sk in stack_events[0]['resource_status'] for sk in stop_keywords):
		for ev in stack_events[startix-1::-1]:
			print(ev_val(ev['time']) + ev['resource_type'].ljust(30) \
						+ ev_val(ev['resource_id']) + ev_val(ev['resource_status']))
	else:
		prev_time = time.time()

		# 1)Start display stack event status when user initiated stack creation,deletion,updating process
		# 2)Call desc_stack_events func every 10 secs to get the list of latest status update
		# 3)Check the length of the list, if curr length > prev length, slice the list to only get the latest event status
		# 4)Run until all the stack process complete or fail
		
		print(ev_val(stack_events[0]['time']) + stack_events[0]['resource_type'].ljust(30) \
			+ ev_val(stack_events[0]['resource_id']) + ev_val(stack_events[0]['resource_status']))
		while True:
			curr_time = time.time()
			if curr_time > prev_time + 10: #Run stuff below for every 10 secs until break
				allev = getEnvironmentStatus(envname)
				if 'event_status' in allev:
					stev = allev['event_status']
					curr_se_length = len(stev)
				else:
					print("%s doesn't exist anymore" % envname)
					return

				prev_time = curr_time

				if curr_se_length > prev_se_length:
					latest_length = curr_se_length - prev_se_length
					for ev in stev[latest_length-1::-1]:
						print(ev_val(ev['time']) + ev['resource_type'].ljust(30) \
							+ ev_val(ev['resource_id']) + ev_val(ev['resource_status']))

					if stev[0]['resource_id'] == envname:
						if stop_keywords[0] in stev[0]['resource_status']:
							process_done = "%s environment process completed." % envname
							print(Style.BRIGHT + process_done)
							break
						elif stop_keywords[1] in stev[0]['resource_status']:
							process_failed = "%s environment process failed." % envname
							print(Style.BRIGHT + process_failed)
							break
						elif stop_keywords[2] in stev[0]['resource_status']:
							update_done = "%s environment update completed." % envname
							print(Style.BRIGHT + update_done)
							break
						elif stop_keywords[3] in stev[0]['resource_status']:
							update_failed = "%s environment update failed." % envname
							print(Style.BRIGHT + update_failed)
							break
					
					prev_se_length = curr_se_length

def displayEnvironmentResource(resp_content):
	if 'error' in resp_content:
		print(resp_content['error'])
	else:
		for res in resp_content['resources']:
			print(res['name'])
			print('Launch On: ' + res['launchon'] + ' GMT')
			print('Private IP: ' + res['privateip'])
			print('Private DNS: ' + res['privatedns'])
			print('Public DNS: ' + res['publicdns'])
			print('Public IP: ' + res['publicip'])
			print('State: ' + res['state'])
			print('-'*30)

def displayStartStopEvents(events):
	if 'status' in events:
		print(events['status'])
	else:
		print(events['error'])

@checkConnection
def listAllEnvironments():
	resp = requests.get(cloudControlurl+get_status_uri,auth=(username,'cc'))
	resp_ctn = json.loads(resp.content)
	if 'error' in resp_ctn:
		print(resp_ctn['error'])

	elif 'environments' in resp_ctn:
		line_width = 25
		header = '\nEnvironment name'.ljust(line_width-3) + 'Resource status'.ljust(line_width) \
					+ 'Created On'.ljust(line_width) + 'Owner'
		print(Style.BRIGHT + header)
		print('-' * len(header))
		for ev in sorted(resp_ctn['environments'],key=lambda ev : ev['name']):
			print(ev['name'].ljust(20),ev['resource_status'].ljust(23),
					ev['create_time'].ljust(25),
					ev['template_desc'].split(':')[0] if ev['template_desc'] else '')
		print('\n')
	else:
		print('No environment.\nTo create: cloudcontrol -c dev or cloudcontrol -c qa\n')

@checkConnection
def listExtensions():
	resp = unirest.get(ext_uri,auth=(username,'cc'))
	print(Style.BRIGHT + '\nList of cloudControl extensions:\n')
	extlist = resp.body.get('extlist','Error listing out cloudControl extensions')
	for ext in extlist:
		print('- %s' % ext)
	print('\nTotal: %d' % len(extlist))

@checkConnection
def runExtension(name,ext_args):
	start = time.time()
	banner = '-'*80 + '\n'
	print(Style.BRIGHT + '\nExecuting %s...\n' % name)
	print(banner)
	headers = {'Content-type':'application/json'}
	data = {'ext_args': ext_args}
	resp = unirest.post(ext_uri + '/' + name,headers=headers,params=json.dumps(data),auth=(username,'cc'))
	extresult = resp.body.get('extresult','Error running the extension')
	print(extresult)
	print(banner)
	end = time.time()
	tottime = end - start
	print('Total time: %.4f secs' % tottime)

def openFile(filepath):
	global configdata
	if '~' in filepath:
		try:
			with open(os.path.expanduser(filepath)) as f:
				configdata = f.read().rstrip('\n')
				return True
		except IOError:
			return False
	else:
		try:
			with open(os.path.realpath(filepath)) as f:
				configdata = f.read().rstrip('\n')
				return True
		except IOError:
			return False

def main():

	def createEnvWithFileHelper():
		#Helper function to create new environment with a custom config file
		if openFile(args.filename):
			createNewEnvironment(args.create)
		else:
			print("File not found")

	#check subp_name first then check the arguments
	if args.subp_name == 'create':
		if args.create:
			createfile = args.create in ['dev','qa'] and args.filename
			createfilewithverb = args.create in ['dev','qa'] and args.filename and args.verbose
			createdefaultwithverb = args.create in ['dev','qa'] and args.verbose
			createdefault = args.create in ['dev','qa']

			if createfilewithverb:
				createEnvWithFileHelper()
			elif createfile:
				createEnvWithFileHelper()
			elif createdefaultwithverb:
				createNewEnvironment(args.create)
			elif createdefault:
				createNewEnvironment(args.create)
			else:
				parser.print_help()

		else:
			print("usage: cloudcontrol create dev OR cloudcontrol create qa")

	elif args.subp_name == 'destroy':
		if args.destroy:
			if args.verbose:
				destroyEnvironment(args.destroy,args.verbose)
			else:
				destroyEnvironment(args.destroy)

		else:
			print("usage: cloudcontrol destroy [ENVIRONMENT_NAME]")

	elif args.subp_name == 'update':
		if args.update and args.filename:
			if openFile(args.filename):
				updateEnvironment(args.update)
			else:
				print("File not found")
		else:
			print("usage: cloudcontrol update [ENVIRONMENT_NAME] -f [UPDATED CUSTOM CONFIG FILEPATH]")

	elif args.subp_name == 'viewevent':
		if args.event_view:
			displayEnvironmentStatus(args.event_view)

	elif args.subp_name == 'list':
		if args.resource:
			getEnvironmentResource(args.resource)
		else:
			listAllEnvironments()

	elif args.subp_name == 'start':
		startEnvironmentResource(args.startenv)
	elif args.subp_name == 'stop':
		stopEnvironmentResource(args.stopenv)

	elif args.subp_name == 'ext':
		if args.subpext_name == 'list':
			listExtensions()
		elif args.subpext_name == 'run':
			if args.ext_name:
				runExtension(args.ext_name,args.ext_args)
			else:
				print('Please enter the extension name')

	else:
		parser.print_help()

if __name__ == '__main__':
	main()

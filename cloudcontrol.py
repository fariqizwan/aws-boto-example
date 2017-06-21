from flask import (
	Flask,
	jsonify,
	request,
	abort,
	url_for,
	make_response
)
from flask.ext.httpauth import HTTPBasicAuth

from awshelper import (
	cmCloudFormTemplateGenerator,
	cmCloudFormStackGenerator,
	cmCloudFormInstance,
	cmAwsEnvNameGenerator
)
from datetime import datetime
import time,os,subprocess32
import logging
import multiprocessing
import configs

app = Flask(__name__)
app.config.from_object('configs.testingConfig')
auth = HTTPBasicAuth()
logger = logging.getLogger('gunicorn.access')

@app.route('/')
def index():
	return "This is cloudControl web service"

@app.route('/cloudcontrol/api',methods=['PUT'])
@auth.login_required
def createEnvironmentRequest():
	if not request.json:
		abort(400)
	newenvtype = request.json['envtype']
	confdata = request.json['configdata']
	if newenvtype not in ['dev','qa']:
		abort(400)
	envname_gen = cmAwsEnvNameGenerator()
	new_env_name = envname_gen.create_new_env_name(newenvtype)#create the new name
	if new_env_name:
		err,nevname = createEnvironment(new_env_name,confdata)
		if err:
			return jsonify({'error':err})
		else:
			status = {
				'env_name':nevname,
				'status_url':url_for('getEnvironmentStatus',envname=nevname,_external=True)
			}
			logger.info('%s [%s] - create %s environment' % (getTimeLog(),auth.username(),nevname))
			return jsonify({'status':status}), 202
	else:
		logger.error('%s [%s] - (error) Unable to create new environment' % (getTimeLog(),auth.username()))
		return jsonify({'error':'Unable to create'})

def createEnvironment(name,confdata):
	'''
	Generate the json template based on the config data

	:param name: new env name created by cmAwsEnvNameGenerator class.

	:param confdata: data from custom config file if available

	:return error message if any, environment name (value replaced if custom env name defined in the config file)
	'''
	cfGen = cmCloudFormTemplateGenerator(confdata,auth.username(),name)
	cfJson,envname = cfGen.generate_cf()#func call to generate json file
	if 'error' in cfJson:
		return cfJson['error'],0
	else:
		## Create the stack based on the generated json template
		cmAwsCF = cmCloudFormStackGenerator()
		os.environ["AWS_START"] = str(int(time.time()))
		error = eval(app.config['CREATE_STACK'])#cmAwsCF.create_stack(envname,cfJson)

		if error:
			print cfJson
			return error.message,0#return error without envname
		else:
			# Run scripts during stack creation
			hosts = cfGen.hosts()
			hosts.sort()
			pidnum	= str(os.getpid())
			os.environ["AWS_ENVNAME"] = envname
			os.environ["AWS_HOSTS"] = ','.join(hosts)
			logger.info("%s [%s] - HOSTS TO BE LAUNCHED: %s" % (getTimeLog(),auth.username(),os.environ["AWS_HOSTS"]))
			os.environ["AWS_USER" ] = auth.username()
			os.environ["AWS_PID"] = pidnum
			# TODO: db host needs to be made dynamically
			os.environ["AWS_DB"] = 'db02'
			createworker = multiprocessing.Process(name='create_%s_%s' % (envname,os.environ["AWS_PID"]),
							target=cloudControlCreateScriptsWorker,args=(envname,pidnum,hosts))
			createworker.start()
			return 0,envname

def cloudControlCreateScriptsWorker(envname,pidnum,hosts):
	'''
	Separate process for running setup scripts

	:param envname: the environment name

	:param pidnum: process id number of the parent process

	return Error message if any
	'''
	logger.info("%s About to run before create scripts" % getTimeLog(pidnum))
	print "%s About to run before create scripts" % getTimeLog(pidnum)
	bfestime = getScriptsEstimatedTime(os.path.join('create',eval(app.config['BEFORE'])))
	checkScriptStatusFile(envname,pidnum)
	cbheader = "\n---- Running initial setup scripts (Estimated time: %d sec) ----\n" % bfestime
	writeScriptStatusToFile(cbheader,envname,pidnum)
	errormsg = runScripts(os.path.join('scripts','create',eval(app.config['BEFORE'])),envname,pidnum)
	if errormsg:
		return

	# Poll for Stack Complete
	sleep = 15
	total_sleep = 0
	done = False
	cmAwsCF = cmCloudFormStackGenerator()
	aws_start = time.time()
	awsestime = getScriptsEstimatedTime('aws')
	awsheader = '\n---- Waiting for AWS to completely bring up all %s resources (Estimated time: %d sec) ----\nWaiting' % (envname,awsestime)
	writeScriptStatusToFile(awsheader,envname,pidnum)
	while not done:
		logger.info("%s Sleeping for %s seconds, %s seconds total" % (getTimeLog(pidnum),sleep,total_sleep))
		print "Sleeping for %s seconds, %s seconds total" % (sleep,total_sleep)
		total_sleep = total_sleep + sleep
		time.sleep(sleep)

		if app.config['TESTING']:
			break

		event_status = cmAwsCF.desc_stack_events(envname)
		if type(event_status) is not str:
			for ev in event_status:
				logger.info("%s envname [ %s ], logical_resource_id [ %s ], resource_status [ %s ]" % (getTimeLog(pidnum),envname,ev.logical_resource_id, ev.resource_status))
				if envname == ev.logical_resource_id and 'CREATE_COMPLETE' == ev.resource_status:
					done = True
					break
				if envname == ev.logical_resource_id and 'ROLLBACK_COMPLETE' == ev.resource_status:
					writeScriptStatusToFile('FAILURE : Error in %s creation, had to rollback!' % (envname),envname,pidnum)
					return
		else:
			writeScriptStatusToFile('FAILURE : %s' % event_status,envname,pidnum)
			return

	aws_timetaken = time.time() - aws_start
	writeScriptRuntimeHistory('aws',aws_timetaken)
	writeScriptStatusToFile('%s resources are up in the cloud...SUCCESS (%d sec)\n' % (envname,int(aws_timetaken)),envname,pidnum)

	logger.info("%s About to run after create scripts" % getTimeLog(pidnum))
	print "%s About to run after create scripts" % getTimeLog(pidnum)
	afestime = getScriptsEstimatedTime(os.path.join('create',eval(app.config['AFTER'])))
	caheader = "\n---- Finalizing environment creation (Estimated time: %d sec) ----\n" % afestime
	writeScriptStatusToFile(caheader,envname,pidnum)
	errormsg = runScripts(os.path.join('scripts','create',eval(app.config['AFTER'])),envname,pidnum)
	if errormsg:
		return

	weblink = '''\nYour Fusion BECOME link -> "https://web01.%s.aws.tm0.com/cgi-bin/admin/tech/become.cgi"
Please use the same credential as your production BECOME.\n''' % envname
	if 'web01' in hosts:
		writeScriptStatusToFile(weblink,envname,pidnum)

	#send signal that scripts processing is done
	writeScriptStatusToFile('\nDone! %s is now ready for use!' % envname,envname,pidnum)

@app.route('/cloudcontrol/api',methods=['DELETE'])
@auth.login_required
def destroyEnvironmentRequest():
	if not request.json:
		abort(400)
	envtodelete = request.json['envname']
	envname_gen = cmAwsEnvNameGenerator()
	env_list = envname_gen.list_available_env_str()

	if envtodelete in env_list:
		os.environ["AWS_START"] = str(int(time.time()))

		destroyEnvironment(envtodelete)

		status = {
			'env_name':envtodelete,
			'status_url':url_for('getEnvironmentStatus',envname=envtodelete)
		}
		logger.info('%s [%s] - destroy %s environment' % (getTimeLog(),auth.username(),envtodelete))
		print '%s [%s] - destroy %s environment' % (getTimeLog(),auth.username(),envtodelete)
		pidnum	= str(os.getpid())
		os.environ["AWS_ENVNAME"] = envtodelete
		os.environ["AWS_USER" ] = auth.username()
		os.environ["AWS_PID"] = pidnum
		# TODO: db host needs to be made dynamically
		os.environ["AWS_DB"] = 'db02'
		destroyworker = multiprocessing.Process(name='destroy_%s_%s' % (envtodelete,os.environ["AWS_PID"]),
							target=cloudControlDestroyScriptsWorker,args=(envtodelete,pidnum))
		destroyworker.start()
		return jsonify({'status':status}), 202
	else:
		logger.error('%s [%s] - (error) destroy %s environment (not found)' % (getTimeLog(),auth.username(),envtodelete))
		return jsonify({'error':'Environment name not found'})

def destroyEnvironment(name):
	cmAwsCF = cmCloudFormStackGenerator()
	cmAwsCF.delete_stack(name)

def cloudControlDestroyScriptsWorker(envname,pidnum):
	'''
	Separate process for running destroy scripts

	:param envname: the environment name

	:param pidnum: process id number of the parent process

	return Error message if any
	'''
	# Run scripts before stack destruction
	logger.info("%s About to run before destroy scripts" % getTimeLog(pidnum))
	print "%s About to run before destroy scripts" % getTimeLog(pidnum)
	dbfestime = getScriptsEstimatedTime(os.path.join('destroy',eval(app.config['BEFORE'])))
	checkScriptStatusFile(envname,pidnum)
	dbheader = "---- Running initial destroy scripts (Estimated time: %d sec) ----\n" % dbfestime
	writeScriptStatusToFile(dbheader,envname,pidnum)
	errormsg = runScripts(os.path.join('scripts','destroy',eval(app.config['BEFORE'])),envname,pidnum)
	if errormsg:
		return
	# Run scripts after stack destruction
	logger.info("%s About to run after destroy scripts" % getTimeLog(pidnum))
	dafestime = getScriptsEstimatedTime(os.path.join('destroy',eval(app.config['AFTER'])))
	daheader = "---- Goodbye %s (Estimated time: %d sec) ----\n" % (envname,dafestime)
	writeScriptStatusToFile(daheader,envname,pidnum)
	errormsg = runScripts(os.path.join('scripts','destroy',eval(app.config['AFTER'])),envname,pidnum)
	if errormsg:
		return
	#send signal that scripts processing is done
	writeScriptStatusToFile('Done!',envname,pidnum)

@app.route('/cloudcontrol/api',methods=['POST'])
@auth.login_required
def updateEnvironmentRequest():
	if not request.json:
		abort(400)
	envtoupdate = request.json['envname']
	confdata = request.json['configdata']
	envname_gen = cmAwsEnvNameGenerator()
	env_list = envname_gen.list_available_env_str()
	if envtoupdate in env_list:
		cfGen = cmCloudFormTemplateGenerator(confdata,auth.username(),envtoupdate)
		cfJson,envname = cfGen.generate_cf()#func call to generate json file
		if 'error' in cfJson:
			return jsonify({'error':cfJson['error']})
		else:
			cmAwsCF = cmCloudFormStackGenerator()
			error = eval(app.config['UPDATE_STACK'])#cmAwsCF.update_stack(envtoupdate,cfJson)
			if error:
				return jsonify({'error':error.message})
			else:
				# Run scripts during stack update
				hosts = cfGen.hosts()
				hosts.sort()
				old_hosts = getCurrentStackMachines(envtoupdate)
				new_hosts = diffStackMachines(old_hosts,hosts)
				new_hosts.sort()
				pidnum	= str(os.getpid())
				os.environ["AWS_ENVNAME"] = envname
				os.environ["AWS_START"] = str(int(time.time()))
				os.environ["AWS_HOSTS"] = ','.join(hosts)
				os.environ["AWS_NEW_HOSTS"] = ','.join(new_hosts)
				logger.info("%s [%s] - HOSTS TO BE LAUNCHED: %s" % (getTimeLog(),auth.username(),os.environ["AWS_HOSTS"]))
				os.environ["AWS_USER" ] = auth.username()
				os.environ["AWS_PID"] = pidnum
				# TODO: db host needs to be made dynamically
				os.environ["AWS_DB"] = 'db02'
				updateworker = multiprocessing.Process(name='update_%s_%s' % (envname,os.environ["AWS_PID"]),
								target=cloudControlUpdateScriptsWorker,args=(envname,pidnum))
				updateworker.start()

				status = {
					'env_name':envname,
					'status_url':url_for('getEnvironmentStatus',envname=envname,_external=True)
				}
				logger.info('%s [%s] - update %s environment' % (getTimeLog(),auth.username(),envtoupdate))
				return jsonify({'status':status}), 202
	else:
		logger.error('%s [%s] - (error) update %s environment (not found)' % (getTimeLog(),auth.username(),envtoupdate))
		return jsonify({'error':'Environment name not found (%s)' % envtoupdate})

def cloudControlUpdateScriptsWorker(envname,pidnum):
	'''
	Separate process for running update scripts

	:param envname: the environment name

	:param pidnum: process id number of the parent process

	return Error message if any
	'''
	logger.info("%s About to run before update scripts" % getTimeLog(pidnum))
	print "%s About to run before update scripts" % getTimeLog(pidnum)
	ubfestime = getScriptsEstimatedTime(os.path.join('update',eval(app.config['BEFORE'])))
	checkScriptStatusFile(envname,pidnum)
	ubheader = "\n---- Running initial update scripts (Estimated time: %d sec) ----\n" % ubfestime
	writeScriptStatusToFile(ubheader,envname,pidnum)
	errormsg = runScripts(os.path.join('scripts','update',eval(app.config['BEFORE'])),envname,pidnum)
	if errormsg:
		return

	# Poll for Stack Complete
	sleep = 15
	total_sleep = 0
	done = False
	cmAwsCF = cmCloudFormStackGenerator()
	aws_start = time.time()
	awsestime = getScriptsEstimatedTime('aws')
	awsheader = '\n---- Waiting for AWS to update %s resources (Estimated time: %d sec) ----\nWaiting' % (envname,awsestime)
	writeScriptStatusToFile(awsheader,envname,pidnum)
	while not done:
		logger.info("%s Sleeping for %s seconds, %s seconds total" % (getTimeLog(pidnum),sleep,total_sleep))
		print "Sleeping for %s seconds, %s seconds total" % (sleep,total_sleep)
		total_sleep = total_sleep + sleep
		time.sleep(sleep)

		if app.config['TESTING']:
			break

		event_status = cmAwsCF.desc_stack_events(envname)
		if type(event_status) is not str:
			for ev in event_status:
				logger.info("%s envname [ %s ], logical_resource_id [ %s ], resource_status [ %s ]" % (getTimeLog(pidnum),envname,ev.logical_resource_id, ev.resource_status))
				if envname == ev.logical_resource_id and 'UPDATE_COMPLETE' == ev.resource_status:
					done = True
					break
				if envname == ev.logical_resource_id and 'UPDATE_ROLLBACK_COMPLETE' == ev.resource_status:
					writeScriptStatusToFile('FAILURE : Error in %s creation, had to rollback!' % (envname),envname,pidnum)
					return
		else:
			writeScriptStatusToFile('FAILURE : %s' % event_status,envname,pidnum)
			return

	aws_timetaken = time.time() - aws_start
	writeScriptRuntimeHistory('aws',aws_timetaken)
	writeScriptStatusToFile('%s resources has been updated...SUCCESS (%d sec)\n' % (envname,int(aws_timetaken)),envname,pidnum)

	logger.info("%s About to run after update scripts" % getTimeLog(pidnum))
	print "%s About to run after update scripts" % getTimeLog(pidnum)
	upestime = getScriptsEstimatedTime(os.path.join('update',eval(app.config['AFTER'])))
	uaheader = "\n---- Finalizing environment update (Estimated time: %d sec) ----\n" % upestime
	writeScriptStatusToFile(uaheader,envname,pidnum)
	errormsg = runScripts(os.path.join('scripts','update',eval(app.config['AFTER'])),envname,pidnum)
	if errormsg:
		return
	#send signal that scripts processing is done
	writeScriptStatusToFile('\nDone! %s is now ready for use!' % envname,envname,pidnum)

@app.route('/cloudcontrol/api/status/<envname>',methods=['GET'])
@auth.login_required
def getEnvironmentStatus(envname):
	cmAwsCF = cmCloudFormStackGenerator()
	envname_gen = cmAwsEnvNameGenerator()
	env_list = envname_gen.list_available_env_str()
	if envname in env_list:
		event_status = cmAwsCF.desc_stack_events(envname)
		date_format = '%d/%m %X %p'
		f_env_status = []
		for ev in event_status:
			status = {
				'time':ev.timestamp.strftime(date_format),
				'resource_type':ev.resource_type,
				'resource_id':ev.logical_resource_id,
				'resource_status':ev.resource_status,
				'resource_status_reason':ev.resource_status_reason
			}
			f_env_status.append(status)
		logger.info('%s [%s] - get %s environment status' % (getTimeLog(),auth.username(),envname))
		return jsonify({'event_status':f_env_status})
	else:
		logger.error('%s [%s] - (error) get %s environment status (not found)' % (getTimeLog(),auth.username(),envname))
		return jsonify({'error':'Environment name not found (%s)' % envname})

@app.route('/cloudcontrol/api/resource/<envname>',methods=['GET'])
@auth.login_required
def getEnvironmentResources(envname):
	aws_inst = cmCloudFormInstance()
	unf_resources = getResourceIds(envname)#unfiltered resource ids
	resources = []
	if unf_resources:
		f_inst_ids = [iid for iid in unf_resources if 'i-' in iid]
		f_dns_rec = [rec for rec in unf_resources if 'aws.tm0' in rec]
		gr_index = [0]#we use this since Python list is a mutable object

		def _getPubDns():#get public dns if any
			try:
				if 'com' in f_dns_rec[gr_index[0]+1]:
					gr_index[0] += 1
					return f_dns_rec[gr_index[0]]
				else:
					return 'None'
			except:
				return 'None'

		for id in f_inst_ids:
			inst = aws_inst.get_instance_detail(id)
			resource = {
				'name':inst['Name'],
				'launchon':inst['LaunchOn'],
				'architecture':inst['Architecture'],
				'privateip':inst['PrivateIP'],
				'publicip':inst['PublicIP'],
				'state':inst['State'],
				'privatedns':f_dns_rec[gr_index[0]],
				'publicdns':_getPubDns()
			}
			resources.append(resource)
			gr_index[0] += 1
		logger.info('%s [%s] - get %s environment resources' % (getTimeLog(),auth.username(),envname))
		return jsonify({'resources':resources})

	else:
		logger.error('%s [%s] - (error) get %s environment resources (not found)' % (getTimeLog(),auth.username(),envname))
		return jsonify({'error':'Environment name not found'})

@app.route('/cloudcontrol/api/resource/<envname>/start',methods=['PUT'])
@auth.login_required
def putEnvironmentStart(envname):
	aws_inst = cmCloudFormInstance()
	unf_resources = getResourceIds(envname)
	if unf_resources:
		f_inst_ids = [iid for iid in unf_resources if 'i-' in iid]
		if aws_inst.get_instance_detail(f_inst_ids[0])['State'] == 'running':
			return jsonify({'status':'%s already started' % envname})
		else:
			start_list = aws_inst.start_instances(f_inst_ids)
			logger.info('%s [%s] - start %s environment' % (getTimeLog(),auth.username(),envname))
			return jsonify({'status':'Starting %s' % envname})
	else:
		logger.error('%s [%s] - (error) start %s environment (not found)' % (getTimeLog(),auth.username(),envname))
		return jsonify({'error':'Environment name not found'})

@app.route('/cloudcontrol/api/resource/<envname>/stop',methods=['PUT'])
@auth.login_required
def putEnvironmentStop(envname):
	aws_inst = cmCloudFormInstance()
	unf_resources = getResourceIds(envname)#unfiltered resource ids
	if unf_resources:
		f_inst_ids = [iid for iid in unf_resources if 'i-' in iid]
		if aws_inst.get_instance_detail(f_inst_ids[0])['State'] == 'stopped':
			return jsonify({'status':'%s already stopped' % envname})
		else:
			stop_list = aws_inst.stop_instances(f_inst_ids)
			logger.info('%s [%s] - stop %s environment' % (getTimeLog(),auth.username(),envname))
			return jsonify({'status':'Stopping %s' % envname})
	else:
		logger.error('%s [%s] - (error) stop %s environment (not found)' % (getTimeLog(),auth.username(),envname))
		return jsonify({'error':'Environment name not found'})

def getResourceIds(envname):
	cmAwsCF = cmCloudFormStackGenerator()
	envname_gen = cmAwsEnvNameGenerator()
	env_list = envname_gen.list_available_env_str()
	if envname in env_list:
		stackRes = cmAwsCF.list_stack_resources(envname)
		inst_ids = [res.physical_resource_id for res in stackRes]
		return inst_ids
	else:
		return None

def getCurrentStackMachines(envname):
	'''
	Get current machine names of an environment

	:param envname: the environment name being requested

	:return List of the environment machine names
	'''
	aws_inst = cmCloudFormInstance()
	unf_resources = getResourceIds(envname)#unfiltered resource ids of that environment
	if unf_resources:
		f_inst_ids = [iid for iid in unf_resources if 'i-' in iid]
		env_mnames = []
		for i in f_inst_ids:
			env_mnames.append(aws_inst.get_instance_detail(i)['Name'].rstrip('.'+envname.upper()))
		return env_mnames
	else:
		return None

def diffStackMachines(curr_mach,updt_mach):
	'''
	Get the difference of instances between current env and the updated one

	:param curr_mach: list of machines in the current environment

	:param updt_mach: list of machines in the updated template

	:return List of machines that are not available in both list
	'''
	if len(curr_mach) > len(updt_mach):
		return []
	else:
		cmset = set(curr_mach)
		newt = [m for m in updt_mach if m not in cmset]
		return newt
	##updt_mach must be longer than curr_mach in order for this to work
	##based on http://stackoverflow.com/questions/3462143/get-difference-between-two-lists, Mark Byers answer
	##because it's fast

@app.route('/cloudcontrol/api/status',methods=['GET'])
@auth.login_required
def getEnvironmentList():
	envname_gen = cmAwsEnvNameGenerator()
	env_list_stat = envname_gen.list_available_env_stat()
	evlist_status = [{'name':ev[0],'resource_status':ev[1],
						'create_time':ev[2].strftime('%d-%b-%Y %H:%M GMT'),
						'template_desc':ev[3]} for ev in env_list_stat]
	logger.info('%s [%s] - list environments request' % (getTimeLog(),auth.username()))
	return jsonify({'environments':evlist_status})

@app.route('/cloudcontrol/api/status/getevnamenpid',methods=['GET'])
def getEnvnameAndPidRequest():
	'''
	Get current environment name in the making and the process id number

	:param None

	:return Environment name and the process id number
	'''
	curr_pidf = os.path.join('/tmp','currentccpid')
	with open(curr_pidf) as f:
		curr_pid = f.read()
	return jsonify({'result':curr_pid})

@app.route('/cloudcontrol/api/status/<envname>/<pid>',methods=['GET'])
def getScriptStatusRequest(envname,pid):
	'''
	Get the current script that is running

	:param envname: the environment name involved

	:param pid: the id of the process that responsible writing the status

	:return a message that display current executing script
	'''
	fpath = os.path.join('/tmp',envname+'_'+pid+'.status')
	try:
		with open(fpath) as f:
			curr_stat = f.read()
			last_stat = curr_stat.split('\n')[-1]
			if 'Done!' in last_stat or 'FAILURE' in last_stat:
				os.remove(fpath)#clean up
			return jsonify({'script_status':curr_stat}), 202
	except IOError:
		logger.error('%s [%s] - (error 13) Invalid file name (%s)' % (getTimeLog(),auth.username(),fpath))
		return jsonify({'error':'Invalid file name (%s)' % fpath})

def runScripts(path,envname,pidnum):
	'''
	Run scripts in a folder, in order

	:param path: relative path

	:param envname: environment name

	:param pidnum: process id number of the parent process

	:return None
	'''
	files = filter(os.path.isfile,[os.path.join(path,f)\
				for f in os.listdir(path) \
					if f.split('_')[0].isdigit() and f.split('_')[-1].isalnum()])
	files.sort()
	tot_files = len(files)
	tot_time = 0
	file_no = 1
	banner = '-'*80
	for f in files:
		status_msg = '%s [%s] - Executing scripts for %s environment [ %s ]' % (getTimeLog(pidnum),auth.username(),envname,f)
		logger.info(status_msg)
		print status_msg
		f_name = f.split('/',3)[-1]
		script_status = '[ %2d of %2d ] Executing %s' % (file_no,tot_files,f_name)
		writeScriptStatusToFile(script_status,envname,pidnum)
		try:
			start_time = time.time()
			out = subprocess32.check_output([ f ])
			end_time = time.time()
			time_diff = end_time - start_time
			tot_time += time_diff
			writeScriptStatusToFile("...SUCCESS (%d sec)\n" % (time_diff),envname,pidnum)
			logger.info('%s SUCCESS [ %s ]' % (getTimeLog(pidnum),f))
			logger.info(banner)
			logger.info(out.rstrip('\n'))
			logger.info(banner)
		except subprocess32.CalledProcessError as e:
			logger.info('%s' % e.output)
			errmsg = 'FAILURE [ PID %s ] [ %s ] EXITED WITH CODE [ %s ]' % (pidnum,f,e.returncode)
			logger.info('%s %s' % (getTimeLog(pidnum),errmsg))
			writeScriptStatusToFile(errmsg,envname,pidnum)
			return errmsg
		file_no += 1

	writeScriptRuntimeHistory(path.split('/',1)[1],tot_time)

def checkScriptStatusFile(envname,pid):
	'''
	Check environment status file existence. If it exist, remove it.
	Only to be used at the beginning of create,update and destroy process.

	:param envname: the environment name involved

	:param pid: the id of the process that call this function

	:return None
	'''
	envpid = envname+'_'+pid
	fpath = os.path.join('/tmp',envpid + '.status')
	if os.path.isfile(fpath):
		os.remove(fpath)

def writeScriptStatusToFile(msg,envname,pid):
	'''
	Write the name of the script that is currently running to a temp file.

	:param msg: The message to be written into the file

	:param envname: the environment name involved

	:param pid: the id of the process that responsible writing the status

	:return None
	'''
	envpid = envname+'_'+pid
	curr_pidf = os.path.join('/tmp','currentccpid')
	with open(curr_pidf,'w') as f:
		f.write(envpid)
	fpath = os.path.join('/tmp',envpid + '.status')
	with open(fpath,'a') as f:
		f.write(msg)

def writeScriptRuntimeHistory(path,time):
	'''
	Write total running time of a script

	:param path: the path of the scripts

	:param time: time taken to execute the script

	:return None
	'''
	historypathf = os.path.join('history',path,'timetaken')
	timelist = []
	try:
		with open(historypathf) as f:
			timelist = f.readlines()
	except IOError:
		pass
	if len(timelist) > 9:
		timelist.pop(0)
	timelist.append(str(time)+'\n')
	with open(historypathf,'w') as f:
		f.writelines(timelist)

def getScriptsEstimatedTime(path):
	'''
	Calculate the average time taken to process scripts

	:param path: the current folder path of 'timetaken'

	:return int: the average time taken to process scripts
	'''
	ttpath = os.path.join('history',path,'timetaken')
	try:
		with open(ttpath) as f:
			ftt = [float(t.rstrip('\n')) for t in f]
			return int(sum(ftt)/len(ftt))
	except IOError:
		with open(ttpath,'w') as f:
			timelist = ['60\n' for i in range(10)]
			f.writelines(timelist)
			return 60#default number

@app.route('/cloudcontrol/api/ext',methods=['GET'])
@auth.login_required
def listExtensions():
	'''
	List available extensions in cloudControl extension folder

	:param None

	:return str: jsonified list of of available extensions
	'''
	extlist = os.listdir('extensions')
	return jsonify({'extlist': extlist})

@app.route('/cloudcontrol/api/ext/<extpath>',methods=['POST'])
@auth.login_required
def runExtensions(extpath):
	'''
	Run selected extension script

	:param path: the path of the extension script

	:return str: jsonified results of the extension script
	'''
	if not request.json:
		abort(400)
	ext_args = request.json['ext_args']
	extlist = os.listdir('extensions')
	extresult = ''
	if extpath in extlist:
		extfile = os.path.join('extensions',extpath)
		ext_args.insert(0,extfile)
		try:
			extresult = executeScript(ext_args)
		except scriptsException as e:
			extresult = e.output
	else:
		extresult = "'%s' is nowhere to be found" % extpath
	return jsonify({'extresult':extresult})

def getTimeLog(pid=str(os.getpid())):
	'''
	Get current time and date

	:return time and date string with the format [Year/Month/Day Hour:Minute:Seconds.Microseconds]
	'''
	return '[%s]' % str(datetime.now().strftime('%d/%b/%Y %H:%M:%S.%f')) + ' [PID: %s]' % pid

@app.route('/cloudcontrol/api',methods=['GET'])
def cloudControlOk():
	'''
	Simple server check status

	return string one
	'''
	return "1"

@app.errorhandler(404)
def not_found(error):
	return make_response(jsonify({'error':'Not found'}),404)

@app.errorhandler(400)
def bad_request(error):
	return make_response(jsonify({'error':'Bad request'}),400)

@auth.get_password
def authenticate(username):
	userlist = ['fizwan','fariqizwan','fariq','pravin','felix','azlina','razak','yevgeny','jay']
	if username in userlist:
		return 'cc'
	return None

@auth.error_handler
def unauthorized():
	logger.error('%s [%s] - (error) Unauthorized access (no permission)' % (getTimeLog(),auth.username()))
	return make_response(jsonify({'error':'Unauthorized access'}),401)

def executeScript(cmd):
	'''
	Execute cloudControl extension script. It will get the output of the script line by line

	:type: list

	:param cmd: The command and its argument that are going to be executed

	:return (str) The output of the script
	'''
	process = subprocess32.Popen(cmd,stdout=subprocess32.PIPE,stderr=subprocess32.STDOUT)
	extoutput = ''
	banner = '-'*80 + '\n'
	while True:
		nextline = process.stdout.readline()
		if nextline == '' and process.poll() != None:
			break
		if nextline != '':
			extoutput += nextline
	output = process.communicate()[0]
	exitcode = process.returncode
	if exitcode == 0:
		return extoutput
	else:
		raise scriptsException(exitcode,cmd,extoutput)

class scriptsException(Exception):
	def __init__(self,exitcode,cmd,output):
		self.exitcode = exitcode
		self.cmd = cmd
		self.output = output

if __name__ == '__main__':
	app.run(port=5000,debug=True)

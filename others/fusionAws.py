import argparse
from colorama import init,Fore,Back,Style
from cfgenerator import cmCloudFormTemplateGenerator
from cfstackgen import cmCloudFormStackGenerator
from cfinstance import cmCloudFormInstance
from simpledb import cmAWSSimpleDB

awsregion = "ap-southeast-2"
awsaccesskey = 'Your AWS access key'
awssecretkey = 'Your AWS secret key'

parser = argparse.ArgumentParser(description="Fusion AWS tool",prog="python fusionAws.py")
parser.add_argument('-i','--interactive',action="store_true",help="Run Fusion AWS tool in interactive mode")
parser.add_argument('-c','--create',nargs='?',const=None,help="Create a new environment using the supplied environment name. Ex: -c dev01")
parser.add_argument('-u','--update',nargs='?',const=None,help="Update an environment based on environment name. Ex: -u dev01")
parser.add_argument('-d','--destroy',nargs='?',const=None,help="Destroy an environment based on environment name. Ex: -d dev01")
parser.add_argument('-l','--listenv',action="store_true",help="List all running environment in AWS.")

args = parser.parse_args()
init(autoreset=True)

tab = lambda x : ''.ljust(10) + Style.BRIGHT+x

def interactiveMode():
	"""
	UI for interactive mode
	"""
	print Fore.GREEN + "Fusion AWS tool. Please select one of the options:"
	print tab("1) Create Environment")
	print tab("2) View Environment Resources")
	print tab("3) Update Environment")
	print tab("4) Destroy Environment")
	print tab("5) Cancel")
	opt = input(":")
	
	def iveCreate():
		envname = selectEnvType()
		if envname:
			#print envname
			createEnv(envname)
		else:
			print Fore.YELLOW + "No new environment available or invalid selection"
	def iveViewStackRes():
		envname = listSelectRunningEnvNames("Please select the environment name to view its resources:")
		if envname:
			viewEnvResource(envname)
	def iveUpdate():
		envname = listSelectRunningEnvNames("Please select the environment name to update:")
		if envname:
			updateEnv(envname)
	def iveDestroy():
		envname = listSelectRunningEnvNames("Please select the environment name to destroy:")
		if envname:
			destroyEnv(envname)
	def iveCancel():
		print Fore.CYAN + 'Canceled'
		
	options = {'1':iveCreate,
			'2':iveViewStackRes,
			'3':iveUpdate,
			'4':iveDestroy,
			'5':iveCancel}
	if opt in options:
		options[opt]()
	else:
		print Fore.YELLOW + "Invalid selection"
	
def createEnv(name):
	## Generate the json template based on the config file
	confpath = 'configs/machineconfig.json'
	cfGen = cmCloudFormTemplateGenerator(confpath)
	cfJson = cfGen.generate_cf()#func call to generate json file
	
	## Create the stack based on the generated json template
	cmAwsCF = cmCloudFormStackGenerator(awsregion,awsaccesskey,awssecretkey)
	cmAwsCF.create_stack(name,cfJson)
	
def viewEnvResource(name):
	cmAwsCF = cmCloudFormStackGenerator(awsregion,awsaccesskey,awssecretkey)
	aws_inst = cmCloudFormInstance(awsregion,awsaccesskey,awssecretkey)
	
	stackRes = cmAwsCF.list_stack_resources(name)
	line_width = 20
	res_header = 'Name'.ljust(line_width)+'Stack'.ljust(line_width)+'Launch On'.ljust(line_width)+'Architecture'.ljust(line_width)+'Private IP'.ljust(line_width)+'Public IP'
	print Fore.BLUE + Style.BRIGHT + res_header
	print Fore.MAGENTA + '='*len(res_header)
	for res in stackRes:
		inst = aws_inst.get_instance_detail(res.physical_resource_id)
		print inst['Name'].ljust(line_width)+inst['Stack'].ljust(15)+inst['LaunchOn'].ljust(25)+inst['Architecture'].ljust(line_width)+inst['PrivateIP'].ljust(line_width)+inst['PublicIP'].ljust(line_width)
		
	
def updateEnv(name):
	print "Update the %s environment" % name
	
def destroyEnv(name):
	cmAwsCF = cmCloudFormStackGenerator(awsregion,awsaccesskey,awssecretkey)
	cmAwsCF.delete_stack(name)
	cmAwsDB = cmAWSSimpleDB(awsregion,awsaccesskey,awssecretkey)
	cmAwsDB.release_env_name(name)
	
def listEnv():
	cmCloudFormStackGenerator(awsregion,awsaccesskey,awssecretkey).list_stacks()
	
def selectEnvType():
	"""
	Command line UI to select the env type to be created
	
	:param None
	
	:return New env name(string) if available else return None
	"""
	envtype = {'1':'dev','2':'qa'}
	print Fore.GREEN + "Please select the environment type:"
	print tab("1) Dev")
	print tab("2) Qa")
	opt = input(":")
	
	if opt in envtype:
		cmAwsDB = cmAWSSimpleDB(awsregion,awsaccesskey,awssecretkey)
		newenvname = cmAwsDB.get_new_env_name(envtype[opt])
		return newenvname
	else:
		return None
		
def listSelectRunningEnvNames(question):
	"""
	Command line UI to list and select the name of env to be destroyed or updated
	
	:param question: The question string to tell user the intent
	
	:return Selected env name(string)
	"""
	cmAwsDB = cmAWSSimpleDB(awsregion,awsaccesskey,awssecretkey)
	envnamelist = cmAwsDB.get_running_env_list()
	if envnamelist:
		index = 1
		print Fore.GREEN + question
		envnamelist.append('Cancel')
		for evname in envnamelist:
			evchoice = "%s) %s" % (index,evname)
			print tab(evchoice)
			index += 1
	else:
		print Fore.YELLOW + "Sorry, no active environment is running right now"
		return
		
	try:
		opt = int(input(":"))
		if opt > 0 and opt < len(envnamelist):
			return envnamelist[opt-1]
		elif opt == len(envnamelist):
			print Fore.CYAN + 'Canceled'
		else:
			print "Invalid selection"
	except:
		print "Invalid input"

def main():
	if args.interactive:
		interactiveMode()
	elif args.create:
		createEnv(args.create)
	elif args.update:
		updateEnv(args.update)
	elif args.destroy:
		destroyEnv(args.destroy)
	elif args.listenv:
		listEnv()
	else:
		interactiveMode()
		
if __name__ == '__main__':
	#For compatibility between Python 2.X and 3.X
	#based on http://stackoverflow.com/questions/954834/how-do-i-use-raw-input-in-python-3-1
	try:
		input = raw_input
	except NameError:
		pass
	main()

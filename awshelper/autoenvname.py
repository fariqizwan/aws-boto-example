import boto.cloudformation
from awsconfigs import awsregion,awsaccesskey,awssecretkey

class cmAwsEnvNameGenerator(object):
	"""
	A class that able to auto-generate new environment name in EC2 and list all environment names
	"""
	def __init__(self):
		self.cfconn = boto.cloudformation.connect_to_region(awsregion,aws_access_key_id=awsaccesskey,aws_secret_access_key=awssecretkey)
		self.envlimit = 50 #total number of environment that we can have
		self.stackstatfilter_list = ['CREATE_COMPLETE','CREATE_IN_PROGRESS',
										'UPDATE_COMPLETE','UPDATE_IN_PROGRESS',
										'UPDATE_ROLLBACK_COMPLETE','UPDATE_ROLLBACK_IN_PROGRESS',
										'DELETE_IN_PROGRESS',
										'ROLLBACK_IN_PROGRESS','ROLLBACK_COMPLETE']

	def list_running_env_type_num(self,envtype):
		"""
		Query AWS for the running environments type
		:param envtype: Environment type (dev/qa)
		:return List of sorted numbers for the environment type or None
		"""
		stack_list = self.cfconn.list_stacks(stack_status_filters=self.stackstatfilter_list)
		currtype_envs = [s.stack_name for s in stack_list if s.stack_name.find(envtype) == 0]
		envt_numlist = [int(e.lstrip(envtype)) for e in currtype_envs]
		return envt_numlist

	def list_available_env_str(self):
		"""
		Query AWS for all environment names available
		:param None
		:return List of environment names in AWS
		"""
		stack_list = self.cfconn.list_stacks(stack_status_filters=self.stackstatfilter_list)
		all_envs = [s.stack_name for s in stack_list]
		return all_envs

	def list_available_env_stat(self):
		"""
		Query AWS for all environment names available with status
		:param None
		:return List of tuple for environment names in AWS with its status
		"""
		stack_list = self.cfconn.list_stacks(stack_status_filters=self.stackstatfilter_list)
		all_envs_stat = [(s.stack_name,s.stack_status,s.creation_time,s.template_description) for s in stack_list]
		return all_envs_stat

	def create_new_env_name(self,envtype):
		"""
		Create new environment name
		:type string
		:param envtype: Environment type (dev/qa)
		:return New environment name(string), return None if there is no more name available
		"""
		env_range = range(1,self.envlimit+1)
		envlist = self.list_running_env_type_num(envtype)
		if not envlist:
			#no env with this envtype, we start with 01
			return envtype + '01'
		elif envlist:
			if len(envlist) == len(env_range):
				return None
			else:
				for i in env_range:
					if i not in envlist:
						#append envtype with i and return
						return envtype + str(i).zfill(2)
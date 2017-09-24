import boto.sdb

class cmAWSSimpleDB(object):
	"""
	Connect to AWS SimpleDB that store list of environments available
	
	Domain: Env_list
	
			|in_use		|category
	---------------------------------------------
	dev-01	| False		| dev
	---------------------------------------------
	qa-02	| True		| qa
	
	:parameter 1 - aws region
	:parameter 2 - aws access key
	:parameter 3 - aws secret key
	"""
	def __init__(self,awsregion,awsaccesskey,awssecretkey):
		self.sdbconn = boto.sdb.connect_to_region(awsregion,aws_access_key_id=awsaccesskey,aws_secret_access_key=awssecretkey)
		self.domain_name = 'Env_list'
		self.envlist_dom = self.sdbconn.get_domain(self.domain_name)
		
	def get_new_env_name(self,env_type):
		"""
		Get new environment name that's available from db.
		
		:type string
		
		:param env_type: Environment type (dev/qa)
		
		:return New environment name (string), return None if there are no more names available
		"""
		query = 'select * from %s where category="%s" and in_use="False"' % (self.domain_name,env_type)
		env_qresult = self.envlist_dom.select(query)
		unuse_envnames = []
		for item in env_qresult:
			unuse_envnames.append(item)
		if unuse_envnames:
			unuse_envnames[0]['in_use'] = True
			unuse_envnames[0].save()
			return unuse_envnames[0].name
		else:
			return None
		
		
	def release_env_name(self,env_name):
		"""
		Release environment name when stack destroyed.
		
		:type string
		
		:param env_name: Environment name (dev_1/qa_2)
		
		:return Result of the operation (boolean)
		"""
		env_item = self.envlist_dom.get_item(env_name)
		if env_item:
			env_item['in_use'] = False
			env_item.save()
			return True
		else:
			return False
		
	def get_running_env_list(self):
		"""
		Get running environments list in AWS.
		
		:param None
		
		:return A list of running environment names(string),return None if no environment in use
		"""
		query = 'select * from %s where in_use="True"' % (self.domain_name)
		env_qresult = self.envlist_dom.select(query)
		running_envlist = []
		for item in env_qresult:
			running_envlist.append(item.name)
		if running_envlist:
			return running_envlist
		else:
			return None
		
	def _reset_Env_list(self):
		"""
		Reset environment name list. All env names will set the 'in_use' attributes to False
		You should not use this.
		
		:param None
		
		:return None
		"""
		#Delete all items in domain
		query = 'select * from %s' % self.domain_name
		qresult = self.envlist_dom.select(query)
		for item in qresult:
			print item.delete()
		
		#Define db structure (dictionary/hash)
		env_types = ['dev','qa']
		env_attr_names = ['in_use','not_use']
		env_attrs_vals = range(1,11)
		
		items = {}
		for et in env_types:
			for i in env_attrs_vals:
				env_name = et + str(i).zfill(2)
				items[env_name] = {'in_use':False,'category':et}
		
		self.envlist_dom.batch_put_attributes(items)

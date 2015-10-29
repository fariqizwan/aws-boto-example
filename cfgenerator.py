from troposphere import Base64, FindInMap, GetAtt
from troposphere import Parameter, Output, Ref, Template
import troposphere.ec2 as ec2
import troposphere.route53 as route53
from bunch import Bunch
import json,yaml
import os,re

class cmCloudFormTemplateGenerator(object):
	"""
	A class to generate cloud formation template
	
	:param json formatted aws instance configuration file name
	
	:return json formatted Cloud Formation Template by calling generate_cf()
	"""
	def __init__(self,configdata,owner,envname):
		self.configdata = configdata
		self.owner = owner
		self.envname = envname
		self.subnet = {'public':'subnet-somenumber1','private':'subnet-somenumber2'}#north california vpc ids
		self.sg = {'publicsecgroup':'sg-somenumber1','privatesecgroup':'sg-somenumber2'}
		self.keyname = 'keyname'
		self.settingsmap = 'configs/profiles/config.conf'
		self.allowedprops = ['instance_type','user_data','security_group','ami_id']
		self.machinelist = []#will be only populate machine names after generate_cf has been called

	def generate_cf(self):
		"""
		Create Cloud Formation Template from user supplied or default config file

		:return json string
		"""
		## read machine list from the config file ##
		machines = self._readConfig(self.configdata)
		if 'error' in machines:
			return machines
		template = Template()
		template.add_description(
				"%s: [%s]" % (self.owner,", ".join(self.machinelist))
			)
		## convert the params into cloud formation instance object ##
		for subnet in machines:
			for mclass in machines[subnet]:
				machine = machines[subnet][mclass]
				instance = self._set_instance_value(machine,mclass,self.subnet[subnet])
				template.add_resource(instance)
				intrecordset = self._set_internal_resource_record(mclass)
				template.add_resource(intrecordset)
				if subnet == 'public':
					pubrecordset = self._set_public_resource_record(mclass)
					template.add_resource(pubrecordset)
		## this magic function turn it to jason formatted template ##
		return template.to_json(),self.envname

	def hosts(self):
		"""
		Get list of hosts for the current environment, derived from the config file

		:return a list of machine names for the environment
		"""
		return self.machinelist

	def _set_instance_value(self,machine,mclass,subnetid):
		"""
		Set the instance settings based on the default/custom machine configs file

		:param machine: the machine settings (Bunch type)

		:param mclass: the machine name

		:param imageid: the machine AMI ID

		:return Troposphere ec2 instance object
		"""
		if 'depends_on' in machine:
			instance = ec2.Instance(mclass,ImageId = machine.ami_id,
						InstanceType = machine.instance_type,
						KeyName = self.keyname,
						SubnetId = subnetid,
						SecurityGroupIds = [self.sg[machine.security_group]],#Ref1
						Tags = [{"Key":"Name","Value":mclass+'.'+self.envname.upper()},
								{"Key":"Owner","Value":self.owner}],
						UserData = Base64(self._readUserData(machine.user_data,mclass)),
						DependsOn = [m+'01' for m in machine.depends_on.split(',')]#since any single machine name now will start with 01
					)
		else:
			instance = ec2.Instance(mclass,ImageId = machine.ami_id,
						InstanceType = machine.instance_type,
						KeyName = self.keyname,
						SubnetId = subnetid,
						SecurityGroupIds = [self.sg[machine.security_group]],#Ref1
						Tags = [{"Key":"Name","Value":mclass+'.'+self.envname.upper()},
								{"Key":"Owner","Value":self.owner}],
						UserData = Base64(self._readUserData(machine.user_data,mclass))
					)
		return instance

	def _set_internal_resource_record(self,mclass):
		"""
		Set the internal dns name for the instance

		:param mclass: the machine name

		:return Private resource record for the instance
		"""
		intDnsZone = 'aws.tm0.internal.'
		recordset = route53.RecordSetType(mclass+'PrivDNSRecord',
						HostedZoneName=intDnsZone,
						Name=mclass+'.'+self.envname+'.'+intDnsZone,
						Type='A',
						TTL='60',
						ResourceRecords=[GetAtt(mclass,'PrivateIp')],
					)
		return recordset

	def _set_public_resource_record(self,mclass):
		"""
		Set the public dns name for the instance

		:param mclass: the machine name

		:return Public resource record for the instance
		"""
		pubDnsZone = 'aws.tm0.com.'
		recordset = route53.RecordSetType(mclass+'PubDNSRecord',
						HostedZoneName=pubDnsZone,
						Name=mclass+'.'+self.envname+'.'+pubDnsZone,
						Type='A',
						TTL='300',
						ResourceRecords=[GetAtt(mclass,'PublicIp')],
					)
		return recordset

	def _readConfigMap(self,filename):
		"""
		Read machine configs map file and convert it to Python dict object

		:type string

		:param Filename of the machine configs map file

		:return dict
		"""
		f = open(filename,'r')
		confd = yaml.load_all(f.read())
		mgroup = {}
		for i in confd:
			keyname = i.keys()[0]
			mgroup[keyname] = i[keyname]
		return Bunch.fromDict(mgroup)

	def _readConfig(self,configdata):
		"""
		Read config file that contains default machine classes or defined by user,
		match with machines map in config.conf and return all the settings

		:type string

		:param Filename of the list of machine classes

		:return list of machine class to be fed into Troposphere
		"""
		mlist = {}
		mmap = self._readConfigMap(self.settingsmap)#get all machine settings map
		#use default config if user does not supply custom config data
		if not configdata:
			confpath = 'configs/profiles/default.conf'
			f = open(confpath,'r')
			configdata = f.read()

		machinelist,cust_conf = self._getTotalMachines(configdata.split('\n'))
		self.machinelist = machinelist
		stripper = lambda x : x.rstrip('0123456789')#strip numbers from the machine name

		for subnet in mmap:
			for hostname in machinelist:
				mapname = stripper(hostname)
				if mapname in mmap[subnet]:#only match machine type within machine settings map
					try:
						mlist[subnet][hostname] = mmap[subnet][mapname]
					except KeyError:
						mlist[subnet] = {}
						mlist[subnet][hostname] = mmap[subnet][mapname]
					#overwrite settings with custom values if any
					if mapname in cust_conf:
						wth = [pkey.encode('utf-8') for pkey in cust_conf[mapname].keys() if pkey not in self.allowedprops]
						if wth:
							return {'error':'Unrecognized instance property key-> %s. Please check your custom config file again.' % wth}
						if 'security_group' in cust_conf[mapname]:
							if self._validateSecurityGroup(cust_conf[mapname]['security_group']):
								mlist[subnet][hostname].security_group = cust_conf[mapname]['security_group']
							else:
								return {'error':'Invalid security group-> %s' % cust_conf[mapname]['security_group']}
						if 'instance_type' in cust_conf[mapname]:
							if self._validateInstanceType(cust_conf[mapname]['instance_type']):
								mlist[subnet][hostname].instance_type = cust_conf[mapname]['instance_type']
							else:
								return {'error':'Invalid instance type-> %s' % cust_conf[mapname]['instance_type']}
						if 'user_data' in cust_conf[mapname]:
							if self._validateUserData(cust_conf[mapname]['user_data']):
								mlist[subnet][hostname].user_data = cust_conf[mapname]['user_data']
							else:
								return {'error':'Invalid userdata file path-> %s (Must be located in the server)' % cust_conf[mapname]['user_data']}
						if 'ami_id' in cust_conf[mapname]:
							if self._validateAmiId(cust_conf[mapname]['ami_id']):
								mlist[subnet][hostname].ami_id = cust_conf[mapname]['ami_id']
							else:
								return {'error':'Invalid AMI id-> %s' % cust_conf[mapname]['ami_id']}

		return Bunch.fromDict(mlist)
		
	def _readUserData(self,filename,mclass):
		"""
		Read user data file
		
		:type string
		
		:param Filename of the user data
		
		:return String containing the user data
		"""
		with open(filename,'r') as f:
			fread = f.read()
			sread = fread.replace('*MNAME',mclass)
			nuserdata = sread.replace('*ENVNAME',self.envname)
			return nuserdata

	def _getTotalMachines(self,machinelist):
			"""
			Helper function to retrieve total machines wanted from the config file

			:param list of machine names from the config file

			:return list of all machines
			"""

			tmlist = []
			cust_conf = {}

			def addMachines(mname):
				"""
				Helper function to create machine names based on their quantity and add it to a list

				:param mname: machine name from config file

				:return machine type that has been added
				"""
				if '=' in mname:
					mtype,num = mname.split('=')
					tmtype = [mtype+str(i).zfill(2) for i in range(1,int(num)+1)]
					tmlist.extend(tmtype)
				elif '.' in mname:#custom defined machine and env name
					#WARNING:this feature should only be use if you know what you're doing
					hostname,envname = mname.split('.')
					self.envname = envname
					if any(s.isdigit() for s in hostname):
						tmlist.append(hostname)
					else:
						tmlist.append(hostname+'01')
					mtype = hostname.strip('0123456789')
				else:#just a single machine
					tmlist.append(mname+'01')
					mtype = mname
				return mtype

			for ms in machinelist:
				if ',' in ms:
					tmp_arr = ms.split(',')
					mtype = addMachines(tmp_arr[0])#!need to validate the machine type
					cust_conf[mtype] = {}#this create a dict of custom settings for the said machine type
					for s in tmp_arr[1:]:
						prop,val = s.split('=')
						cust_conf[mtype][prop.strip()] = val.strip()
				else:
					addMachines(ms)

			return tmlist,cust_conf

	def _validateSecurityGroup(self,sec_group):
		'''
		Check the validity of the security group value read from a custom config file

		:param sec_group: security group name

		:return True/False
		'''
		sec_group_list = ['publicsecgroup',
							'privatesecgroup']

		return sec_group in sec_group_list

	def _validateInstanceType(self,instance_type):
		'''
		Check the validity of the instance type value read from a custom config file

		:param instance_type: instance type name

		:return True/False
		'''
		inst_type_list = ['t2.micro',
							't2.small',
							't2.medium',
							'm3.medium',
							'm3.large',
							'm3.xlarge',
							'c4.large',
							'c4.xlarge',
							'c3.large',
							'c3.xlarge',
							'r3.large',
							'i2.xlarge',
							'd2.xlarge']

		return instance_type in inst_type_list

	def _validateUserData(self,filepath):
		'''
		Check the validity of the user data file passed in through custom config file
		(Currently the user data file must reside inside the server to be valid)

		:param filepath: location of the file

		:return True/False
		'''
		normpath = os.path.normpath(filepath)
		if '~' in normpath:
			try:
				with open(os.path.expanduser(normpath)) as f:
					f.read()
					return True
			except IOError:
				return False
		else:
			try:
				with open(os.path.realpath(normpath)) as f:
					f.read()
					return True
			except IOError:
				return False

	def _validateAmiId(self,ami_id):
		'''
		Check the ami id string for the correct format

		:param ami_id: ami id string

		:return True/False
		'''
		return re.match('^ami-\w{8}$',ami_id)

## References ##
# Ref 1 - http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-ec2-instance.html#cfn-ec2-instance-securitygroups

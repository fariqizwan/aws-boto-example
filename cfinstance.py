import boto.ec2
from datetime import datetime
from awsconfigs import awsregion,awsaccesskey,awssecretkey

class cmCloudFormInstance(object):
	def __init__(self):
		self.conn = boto.ec2.connect_to_region(awsregion,aws_access_key_id=awsaccesskey,aws_secret_access_key=awssecretkey)
		
	def convertAWSTimeString(self,awstime):
		"""
		Convert AWS time string to easier to read format
		
		:type string
		
		:param awstime: time string from aws
		
		:return Time string like this: '09 Mar 2015 06:24:37'
		"""
		awstimeformat = '%Y-%m-%dT%H:%M:%S.000Z'
		prefdate_format = '%d/%m/%Y %H:%M:%S'
		dt = datetime.strptime(awstime,awstimeformat)
		return dt.strftime(prefdate_format)
		
	def get_instance_detail(self,inst_id):
		""""
		Get detail info of an instance
		
		:type string
		
		:param inst_id: The id of the AWS instance
		
		:return A dictionary that contains these keys: Name,Stack,LaunchOn,Architecture,PrivateIP,PublicIP
		"""
		try:
			awsinstance = self.conn.get_only_instances(instance_ids=inst_id)[0]
			inst_dict = {'Name':str(awsinstance.tags['Name']),
							'Stack':str(awsinstance.tags['aws:cloudformation:stack-name']),
							'LaunchOn':self.convertAWSTimeString(awsinstance.launch_time),
							'Architecture':str(awsinstance.architecture),
							'PrivateIP':str(awsinstance.private_ip_address),
							'PublicIP':str(awsinstance.ip_address),
							'State':str(awsinstance.state)}
			return inst_dict
			
		except Exception,e:
			print e

	def start_instances(self,inst_list):
		"""
		Start the instances specified
	
		:type list
	
		:param A list of strings of the instance IDs to start
	
		:return A list of the instances started
		"""
		try:
			inst_list = self.conn.start_instances(instance_ids=inst_list)
			return inst_list
		except Exception,e:
			print e

	def stop_instances(self,inst_list):
		"""
		Stop instances for the given instance id list

		:type list

		:param inst_list: A list of strings of the instance IDs to stop

		:return A list of the instances stopped
		"""
		try:
			inst_list = self.conn.stop_instances(instance_ids=inst_list)
			return inst_list
		except Exception,e:
			print e

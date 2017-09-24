import boto.cloudformation
import boto.route53
import time
from awsconfigs import awsregion,awsaccesskey,awssecretkey

class cmCloudFormStackGenerator(object):
	"""
	A class that create,destroy,list and etc stacks in AWS
	"""
	def __init__(self):
		self.cfconn = boto.cloudformation.connect_to_region(awsregion,aws_access_key_id=awsaccesskey,aws_secret_access_key=awssecretkey)
		self.r53conn = boto.route53.connect_to_region(awsregion,aws_access_key_id=awsaccesskey,aws_secret_access_key=awssecretkey)
		
	def create_stack(self,stack_name,template_json):
		"""
		Create an AWS instance stack using Cloud Formation Template
		
		:type string,string
		
		:param stack_name: Name of the stack
		
		:param template_json: Cloud Formation Template in json formatted string
		
		:return An AWS instance as described in the template
		"""
		try:
			self._delete_pubdnsrec(stack_name)
			self._delete_privdnsrec(stack_name)
			self.cfconn.create_stack(stack_name, template_body=template_json)
							
		except Exception,e:
			return e
			
	def delete_stack(self,stack_name):
		"""
		Destroy an AWS instance stack created  by Cloud Formation Template
		
		:type string
		
		:param stack_name: Name of the stack
		"""
		try:
			self.cfconn.delete_stack(stack_name)
			self._delete_pubdnsrec(stack_name)
			self._delete_privdnsrec(stack_name)
			
		except Exception,e:
			return e

	def update_stack(self,stack_name,template_json):
		"""
		Update existing AWS stack using Cloud Formation Template

		:type string,string

		:param stack_name: Name of the stack

		:param template_json: Cloud Formation Template in json formatted string
		"""
		try:
			self.cfconn.update_stack(stack_name,template_body=template_json)

		except Exception,e:
			return e

	def _delete_pubdnsrec(self,stack_name):
		"""
		Remove the public dns entries of the stack from Route53

		:type string

		:param stack_name: Name of the stack
		"""
		try:
			cmpubdnszone = self.r53conn.get_zone('aws.tm0.com.')
			awspublicdns = cmpubdnszone.get_records()
			stackpublicdns = [rec for rec in awspublicdns if stack_name in rec.name]
			status = cmpubdnszone.delete_record(stackpublicdns)

		except Exception,e:
			return e

	def _delete_privdnsrec(self,stack_name):
		"""
		Remove the private dns entries of the stack from Route53

		:type string

		:param stack_name: Name of the stack
		"""
		try:
			cmprivdnszone = self.r53conn.get_zone('aws.tm0.internal.')
			awsprivatedns = cmprivdnszone.get_records()
			stackprivatedns = [rec for rec in awsprivatedns if stack_name in rec.name]
			status = cmprivdnszone.delete_record(stackprivatedns)

		except Exception,e:
			return e
			
	def list_stacks(self):
		"""
		List all running AWS stacks
		
		:param None
		
		:return List of AWS stacks
		"""
		try:
			stack_list = self.cfconn.list_stacks(stack_status_filters='CREATE_COMPLETE')
			return stack_list
			
		except Exception,e:
			return e
			
	def list_stack_resources(self,stackname):
		""""
		Returns descriptions of all resources of the specified stack
		
		:param stackname: Name of the stack
		
		:return List of the StackResourceSummary objects
		"""
		try:
			stack_resources = self.cfconn.list_stack_resources(stackname)
			return stack_resources
			
		except Exception,e:
			return e

	def list_stack_instances(self,stackname):
		"""
		Find list of instance ids for the stack
		:type string
		:param stackname: Name of the stack
		:return A list of the instance ids in the stack
		"""
		#to be implemented in near future
		pass
			
	def desc_stack_events(self,stackname):
		"""
		Returns stack related events for a specified stack
		
		type: string
		
		:param stackname: Name or ID of the stack
		
		:return StackEvent objects. valid_states = ("CREATE_IN_PROGRESS", "CREATE_FAILED", "CREATE_COMPLETE",
							"DELETE_IN_PROGRESS", "DELETE_FAILED", "DELETE_COMPLETE")
		"""
		try:
			stack_events = self.cfconn.describe_stack_events(stack_name_or_id=stackname)
			return stack_events
			
		except Exception,e:
			return "%s environment doesn't exist anymore or was destroyed." % stackname

class Config(object):
	DEBUG = False
	CREATE_STACK = 'cmAwsCF.create_stack(envname,cfJson)'
	UPDATE_STACK = 'cmAwsCF.update_stack(envtoupdate,cfJson)'
	BEFORE = "'before'"
	AFTER = "'after'"
	TESTING = False

class testingConfig(Config):
	DEBUG = True
	CREATE_STACK = 'cmAwsCF.create_stack(envname,cfJson)'#'0'
	UPDATE_STACK = 'cmAwsCF.update_stack(envtoupdate,cfJson)'#'0'
	BEFORE = "'testbefore'"
	AFTER = "'testafter'"
	TESTING = True


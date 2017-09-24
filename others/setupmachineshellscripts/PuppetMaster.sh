#!/usr/bin/bash

echo 'Setup hostname..'
echo 'puppet01.aws.tm0.internal' > /etc/hostname
sed -i '3ipreserve_hostname :true' /etc/cloud/cloud.cfg

echo 'Fix yum repo...'
sed -i 's/sslverify=1/sslverify=0/g' /etc/yum.repos.d/redhat-rhui.repo
sed -i 's/sslverify=1/sslverify=0/g' /etc/yum.repos.d/redhat-rhui-client-config.repo
yum clean all
	
echo 'Install WGET..'
yum update -y
yum install wget -y

echo 'Configuring EPEL...'
EPEL=$(wget -q -O- https://dl.fedoraproject.org/pub/epel/7/x86_64/e/ | grep epel-release | cut -d\" -f6)
wget https://dl.fedoraproject.org/pub/epel/7/x86_64/e/$EPEL
yum install $EPEL -y
yum repolist
			
echo 'Setup environment variables...'
export AWS_ACCESS_KEY_ID='AKIAJ24JYACAIXVGZKQQ'
export AWS_SECRET_ACCESS_KEY='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'
export AWS_DEFAULT_REGION='ap-southeast-2'
		
echo 'Install & Configure AWS CLI...'
command -v pip-python >/dev/null 2>&1 || { yum install -y python-pip; }
pip install awscli

echo 'Disable SELINUX...'
sed -i '4s/.*/SELINUX=disabled/' /etc/selinux/config
setenforce 0
	
echo 'Setup Packages...'
aws s3 sync s3://s3-pravin/Packages/ /root/packages/.

echo 'Install Apache and all other required packages...'
rpm -Uvh /root/packages/extra_packages/* --force
gem install /root/packages/rack-1.6.0.gem /root/packages/passenger-4.0.57.gem

echo 'Installing puppet server...'
rpm -Uvh /root/packages/Puppet-3.7.3/*
rpm -Uvh /root/packages/PuppetServer-3.7.3/*
echo 'Puppet Server installed!'
aws s3 cp s3://s3-pravin/Conf/puppet.conf /etc/puppet/puppet.conf
echo '*' > /etc/puppet/autosign.conf

echo 'Run Master once for cert creation...'
echo \"node 'default' {}\" > /etc/puppet/manifests/site.pp
service puppetmaster start

echo '--INSTALL & CONFIGURE PASSENGER--'
echo 'Start the passenger-apache2 installer...'
/usr/local/share/gems/gems/passenger-4.0.57/bin/passenger-install-apache2-module --auto

echo 'Apply Puppet VirtualHost Configuration & Rack...'
aws s3 cp s3://s3-pravin/Conf/puppetmaster.conf /etc/httpd/conf.d/puppetmaster.conf
sed -i 's/<domain>/puppet01.aws.tm0.internal/g' /etc/httpd/conf.d/puppetmaster.conf
mkdir -p /usr/share/puppet/rack/puppetmaster/{publictmp} && cd /usr/share/puppet/rack/puppetmaster
aws s3 cp s3://s3-pravin/Conf/config.ru /usr/share/puppet/rack/puppetmaster/config.ru

echo 'Change Ownership on all puppet dirs'
chown -R puppet:puppet /etc/puppet
chown -R puppet:puppet /var/lib/puppet
chown -R puppet:puppet /usr/share/puppet

echo 'Ensure PuppetMaster daemon is stopped and start Apache...'
service puppetmaster stop
service httpd start
echo 'Apache running... All steps complete!'

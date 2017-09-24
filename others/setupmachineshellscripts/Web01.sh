#!/usr/bin/bash

echo 'Setup hostname..'
echo 'web01.aws.tm0.internal' > /etc/hostname
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

echo 'Configure Ext. A Record on Route53...'
mkdir /opt/aws && cd /opt/aws
wget -q http://s3.amazonaws.com/ec2metadata/ec2-metadata
chmod +x ec2-metadata
pip install cli53
ZONE='aws.tm0.com'
TTL='600'
PUB_IP=$(/opt/aws/ec2-metadata | grep ^public-ipv4 | cut -d' ' -f2)
cli53 rrcreate \"$ZONE\" web01 A \"$PUB_IP\" --replace --ttl \"$TTL\"

echo 'Disable SELINUX...'
sed -i '4s/.*/SELINUX=disabled/' /etc/selinux/config
setenforce 0

echo 'Setup Packages...'
aws s3 sync s3://s3-pravin/Packages/ /root/packages/.

echo 'Installing puppet...'
rpm -Uvh /root/packages/extra_packages/* --force
rpm -Uvh /root/packages/Puppet-3.7.3/*
echo 'Puppet installed!'

echo 'Adding puppet config...'
echo 'server=puppet01.aws.tm0.internal' >> /etc/puppet/puppet.conf
echo 'listen=true' >> /etc/puppet/puppet.conf

echo 'Start puppet agent...'
service puppet start

echo 'Done!'

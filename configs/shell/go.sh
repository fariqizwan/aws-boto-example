#!/bin/bash
echo 'Setup hostname..'
hostname go01.*ENVNAME.aws.tm0.internal
echo 'HOSTNAME=go01.*ENVNAME.aws.tm0.internal' >> /etc/sysconfig/network

echo 'Time fix..'
rm /etc/localtime
hwclock --hctosys
ln -s /usr/share/zoneinfo/America/New_York /etc/localtime

echo 'Setup environment variables..'
export AWS_ACCESS_KEY_ID='AKIAJPZT6MS623KKN2ZQ'
export AWS_SECRET_ACCESS_KEY='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'
export AWS_DEFAULT_REGION='us-west-1'

echo 'Configure Ext. A Record on Route53...'
ZONE='aws.tm0.com'
TTL='600'
PUB_IP=$(/opt/aws/bin/ec2-metadata | grep ^public-ipv4 | cut -d' ' -f2)
cli53 rrcreate $ZONE go01.*ENVNAME A $PUB_IP --replace --ttl $TTL

echo 'Put hostname into essentials script..'
sed -i 's/hostname/go01.*ENVNAME/g' /usr/local/ec2/essentials.sh

echo 'Installing puppet...'
rpm -Uvh /root/packages/puppet-3.7.3-1.el6.noarch.rpm
echo 'Puppet installed!'

echo 'Adding puppet config...'
sed -i '13ienvironment=*ENVNAME' /etc/puppet/puppet.conf
echo 'server=puppet01.*ENVNAME.aws.tm0.internal' >> /etc/puppet/puppet.conf
echo 'ignorecache=true' >> /etc/puppet/puppet.conf
echo 'listen=true' >> /etc/puppet/puppet.conf

echo 'Copy updated fqdn fact...'
cp /root/fqdn.rb /usr/lib/ruby/site_ruby/1.8/facter/

echo 'Start puppet agent...'
service puppet start
chkconfig puppet on

echo 'Done!'

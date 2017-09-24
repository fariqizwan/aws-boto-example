#!/bin/bash

echo 'Setup hostname..'
echo 'puppet01.*ENVNAME.aws.tm0.internal' > /etc/hostname
sed -i '3ipreserve_hostname :true' /etc/cloud/cloud.cfg

echo 'Ensure Apache is stopped..'
service httpd stop

yum clean all
yum repolist

echo 'Setup environment variables...'
export AWS_ACCESS_KEY_ID='AKIAJPZT6MS623KKN2ZQ'
export AWS_SECRET_ACCESS_KEY='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'
export AWS_DEFAULT_REGION='us-west-1'

echo 'Add go-server & restart agent...'
sed -i 's/go.aws.tm0.internal/go01.*ENVNAME.aws.tm0.internal/g' /etc/default/go-agent
rm -rf /var/lib/go-agent/config/guid.txt
service go-agent restart

echo 'Run Master once for cert creation...'
echo "node 'default' {}" > /etc/puppet/manifests/site.pp
service puppetmaster start
sleep 20

echo 'Configure puppet..'
sed -i 's/<domain>/puppet01.*ENVNAME.aws.tm0.internal/g' /etc/httpd/conf.d/puppetmaster.conf
sed -i '20i[*ENVNAME]' /etc/puppet/puppet.conf
sed -i '21imodulepath = /etc/puppet/environments/*ENVNAME/modules:/usr/share/puppet/modules' /etc/puppet/puppet.conf
sed -i '22imanifest = /etc/puppet/environments/*ENVNAME/manifests/site.pp' /etc/puppet/puppet.conf

echo 'Puppet Git Repo Setup..'
cd /etc/puppet/environments && git clone git@github.com:/FusionDevOps/puppet.git *ENVNAME
cd /etc/puppet/environments/*ENVNAME && git checkout -b poc origin/poc

echo 'Hiera Git Repo Setup..'
cd /etc/puppet && git clone git@github.com:/FusionDevOps/hiera.git
cd /etc/puppet && cp -r hiera/. .
rm -rf /etc/puppet/hiera

echo 'Change Ownership on all puppet dirs'
chown -R puppet:puppet /etc/puppet
chown -R puppet:puppet /var/lib/puppet
chown -R puppet:puppet /usr/share/puppet

echo 'Ensure PuppetMaster daemon is stopped and start Apache...'
service puppetmaster stop
service httpd start
echo 'Apache running... All steps complete!'

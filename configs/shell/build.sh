#!/bin/bash
echo 'Setup hostname..'
hostname *MNAME.*ENVNAME.aws.tm0.internal
echo 'HOSTNAME=*MNAME.*ENVNAME.aws.tm0.internal' >> /etc/sysconfig/network

echo 'Time fix..'
rm /etc/localtime
hwclock --hctosys
ln -s /usr/share/zoneinfo/America/New_York /etc/localtime

echo 'Put hostname into essentials script..'
sed -i 's/hostname/*MNAME.*ENVNAME/g' /usr/local/ec2/essentials.sh

echo 'Add go-server & restart agent...'
sed -i 's/go.aws.tm0.internal/go01.*ENVNAME.aws.tm0.internal/g' /etc/default/go-agent
rm -rf /var/lib/go-agent/config/guid.txt
service go-agent restart

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

yum makecache

echo 'Installing build tools...'
yum groupinstall -y "Development Tools"
yum groupinstall -y "Debugging Tools"
yum groupinstall -y "Performance Tools"
yum groupinstall -y "Perl Support"
yum groupinstall -y "Emacs"

echo 'Installing packages for release script'
yum install -y perl-CDB_File
yum install -y perl-Date-Manip
yum install -y perl-Template-Toolkit
yum install -y perl-XML-LibXML
yum install -y ctah-usr-share-extjs
yum install -y ctah-usr-share-yuicompressor
yum install -y ctah-rpmbuild-build-bin
yum install -y ctah-aws-repo-scripts
yum install -y rpmrebuild

# TODO: bake into backend image or have puppet do this?
if [ ! -f /home/cloudcat/.ssh/config ]; then
    echo "Creating ssh config for cloudcat"
    echo 'Host *
    StrictHostKeyChecking no' > /home/cloudcat/.ssh/config
    chown cloudcat:cloudcat     /home/cloudcat/.ssh/config
fi

echo 'Done!'


# -*- mode: ruby -*-
# vi: set ft=ruby :

# "local" will be mapped to /etc/repo-deploy in the VM

Vagrant.configure(2) do |config|
  config.vm.box = "ubuntu/trusty64"
  config.vm.provision "shell", inline: <<-SHELL
	# First time setup
	if ! test -d /var/log/ext; then
		sudo apt-get -y update
		sudo apt-get -y install python-pip git
		sudo pip install requests boto sh croniter docker-py
		mkdir /var/log/ext
		echo 'StrictHostKeyChecking no' > /root/.ssh/config
	fi
	cd /vagrant
	sudo rm -rf /etc/repo-deploy
	sudo python setup.py install
	sudo rm -rf /etc/repo-deploy
	sudo ln -s /vagrant/local /etc/repo-deploy
  SHELL
end

"""store juju password in local keyring"""
import keyring
import getpass


username = input('username: ')
password = getpass.getpass('password: ')
keyring.set_password("contrail-config-diff", username, password)

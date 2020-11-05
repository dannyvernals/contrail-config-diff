""" Grab contrail config files and compare them against previous versions
Developing feature to use git as backend storage for the data instead of flat files"""
import subprocess
import sys
import os
import shutil
import filecmp
import pathlib
import argparse
import re
import yaml
import logging
from logging.handlers import RotatingFileHandler
from juju import loop
from juju.model import Model


def logging_func(mode):
    """Instantiate Logging."""
    directory = os.getcwd()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    if not os.path.exists(directory + '/logs'):
        os.makedirs(directory + '/logs')
    handler_file = RotatingFileHandler(directory + '/logs/contrail_config_diff.log',
                                       maxBytes=100000, backupCount=10
                                       )
    handler_file.setLevel(logging.INFO)
    handler_stout = logging.StreamHandler(sys.stdout)
    handler_stout.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler_file.setFormatter(formatter)
    logger.addHandler(handler_file)
    if mode == 'maint':
        logger.addHandler(handler_stout)
    return logger


def read_file(file_path):
    """get text from a file"""
    with open(file_path) as file_handle:
        file_contents = file_handle.read()
    return file_contents


def read_conf_files(unit_ip_file, remote_files):
    """load settings from the specified yaml files"""
    conf_files = yaml.safe_load(read_file(remote_files))
    unit_ips = yaml.safe_load(read_file(unit_ip_file))
    return unit_ips, conf_files


def write_file(contents, file_location):
    """write arbitrary strings to a file"""
    with open(file_location, 'w+') as write_fh:
        write_fh.write(contents)
    os.chmod(file_location, 0o600)


def password_wipe(text_blob):
    """remove passwords from text"""
    new_blob = []
    for line in text_blob.splitlines():
        if 'password' in line.lower() or 'secret' in line.lower():
            if 'auth_type' not in line.lower():
                line = re.split('=| ', line)
                new_blob.append(line[0] + ' #PASSWORD REMOVED#')
            else:
                new_blob.append(line)
        else:
            new_blob.append(line)
    return '\n'.join(new_blob)


def get_remote_file(remote_ip, file_location, username):
    """grab the text contents of a file on a remote system via SSH.
    as most contrail / openstack config files are only root readable
    do this via a sudo cat"""
    try:
        pipes = (subprocess.Popen(['ssh', '-o StrictHostKeyChecking=no',
                                   username + '@{}'.format(remote_ip),
                                   'sudo', 'cat', file_location
                                   ],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE
                                 )
                )
        std_out, std_err = pipes.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        LOGGER.info("No answer from '{}', skipping.".format(remote_ip))
        return "HOST DOWN"
    if pipes.returncode != 0:
        if b'No such file or directory' in std_err:
            return ''
        raise Exception(std_err.strip())
    return std_out.decode('utf-8')


def scrape_server(in_params):
    """grab remote files from a server and save to a local directory,
    if the directory doesn't exist, create it and, if required, it's parents"""
    server_ip, component, files, dir_path, username, inc_passwords = in_params
    LOGGER.info("from '{}'".format(server_ip))
    for conf_loc in files[component]:
        conf_file = get_remote_file(server_ip, conf_loc, username)
        if conf_file == "HOST DOWN":
            break
        if not inc_passwords:
            conf_file = password_wipe(conf_file)
        file_name = conf_loc.replace('/', '_')
        local_path = '{}/{}/{}'.format(dir_path, component, server_ip)
        pathlib.Path(local_path).mkdir(parents=True, exist_ok=True)
        pathlib.Path(local_path).chmod(0o700)
        write_file(str(conf_file), local_path + '/' + file_name)


def write_config_files(unit_ips, files, dir_path, username, inc_passwords):
    """for components endpoints in 'unit_ips' grab config in 'files'
    and dump the file to 'dir'"""
    for component, server_ips in unit_ips.items():
        LOGGER.info("getting '{}' data".format(component))
        for server_ip in server_ips:
            scrape_server((server_ip, component, files, dir_path, username, inc_passwords))
    if 'repos' in dir_path:
        commit_git(dir_path)


def diff_files(old_dir, new_dir, diff_mode):
    """Instantiate a file compare object against the specified directories.
    call 'recurse_diff_files()' to compare all files in those directories"""
    if os.path.exists(old_dir) and os.path.exists(new_dir):
        dcmp = filecmp.dircmp(old_dir, new_dir)
        recurse_diff_files(dcmp, diff_mode)
    else:
        LOGGER.info("missing directory: '{}' or '{}'\nstopping diff".format(old_dir, new_dir))


def get_file_diffs(dcmp, file_name, diff_mode):
    """Echo file diffs to stdout"""
    left_file = dcmp.left + '/' + file_name
    right_file = dcmp.right + '/' + file_name
    if diff_mode == 'context':
        diff_flag = '-c'
    elif diff_mode == 'unified':
        diff_flag = '-u'
    else:
        diff_flag = '--normal'
    diff = (subprocess.Popen(['diff', diff_flag, left_file, right_file],
                             stdout=subprocess.PIPE).communicate()[0]
           )
    print('=' * 100)
    print("{}\n{}".format(left_file, right_file))
    print(diff.decode('utf-8'))


def recurse_diff_files(dcmp, diff_mode):
    """Recurse through all subdirs of 'dcmp' filecmp.dircmp object.
    Return all the files missing and print a diff of all files that are different"""
    if dcmp.diff_files:
        for file_name in dcmp.diff_files:
            get_file_diffs(dcmp, file_name, diff_mode)
    if dcmp.left_only:
        print('=' * 100)
        print("Files missing in the '{}' directory: ".format(dcmp.right))
        print('\n'.join(dcmp.left_only))
    if dcmp.right_only:
        print('=' * 100)
        print("Files missing in the '{}' directory: ".format(dcmp.left))
        print('\n'.join(dcmp.right_only))
    for sub_dcmp in dcmp.subdirs.values():
        recurse_diff_files(sub_dcmp, diff_mode)


async def get_juju_status_api():
    """Connect to current juju model and obtain a status.
    currently reliant on user obtaining an auth macaroon via juju CLI
    TODO: implement local authentication"""
    model = Model()
    #await model.connect(username='admin', password='c0ntrail123')
    await model.connect()
    status = await model.get_status()
    await model.disconnect()
    return status


def parse_juju_status_api(juju_status):
    """parse juju status and generate a list of application IPs
    to be used in a config file that defines the model"""
    ip_unit_map = {}
    for juju_app, juju_app_data in juju_status.applications.items():
        if 'contrail' in juju_app:
            if juju_app_data.subordinate_to:
                for parent_app in juju_app_data.subordinate_to:
                    parent_app_name = juju_status['applications'][parent_app]
                    std_app_name = re.split(':|/', parent_app_name.charm)[-1]
                    std_app_name = '-'.join(std_app_name.split('-')[0:-1])
                    for unit_data in juju_status['applications'][parent_app]['units'].values():
                        ip_unit_map.setdefault(std_app_name, set()).add(unit_data.public_address)
            else:
                std_app_name = re.split(':|/', juju_app_data.charm)[-1]
                std_app_name = '-'.join(std_app_name.split('-')[0:-1])
                for unit_data in juju_app_data.units.values():
                    ip_unit_map.setdefault(std_app_name, set()).add(unit_data.public_address)
    return ip_unit_map


def get_juju_charm_versions(juju_status):
    """parse juju status from the model and return a list of installed
    applications and their versions"""
    status_list = []
    format_string = '{:25} {:50} {:30} {:10}'
    status_list.append(format_string.format('# application', 'charm', 'unit', 'software version'))
    for juju_app, juju_app_data in juju_status.applications.items():
        for unit, unit_data in juju_app_data.units.items():
            status_list.append(format_string.format(juju_app, juju_app_data.charm,
                                                    unit, unit_data.workload_version
                                                    ))
    return '\n'.join(status_list) + '\n'

def check_dir(output_dir):
    """warn if output dir already exists, delete it if user accepts this"""
    if os.path.exists(output_dir):
        while True:
            answer = input("output directory already exists, "
                           "old files will be deleted, proceed?, y/n:"
                          )
            if answer.lower() not in ('y', 'n'):
                print("'y' or 'n' only please")
            else:
                break
        if answer.lower() == 'n':
            exit()
        shutil.rmtree(output_dir)
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)


def commit_git(output_dir):
    """commit changes to the repo
    TODO: move to native from a sub process"""
    os.chdir(output_dir)
    pipes = (subprocess.Popen(['git', 'add', './'],
             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            )
    std_out, std_err = pipes.communicate()
    LOGGER.info(std_out)
    LOGGER.info(std_err)
    pipes = (subprocess.Popen(['git', 'commit', '-m', 'automated commit'], 
             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            )
    std_out, std_err = pipes.communicate()
    LOGGER.info(std_out)
    LOGGER.info(std_err)


def check_dir_git(output_dir):
    """initialize git repo if not done already
    TODO: move to native from a sub process"""
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    if not os.path.exists(output_dir + '/.git'):
        pipes = (subprocess.Popen(['git', 'init', output_dir],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                )
        std_out, std_err = pipes.communicate()
        LOGGER.info(std_out)
        LOGGER.info(std_err)



def cli_grab():
    """take stuff from cli, output it in a dict"""
    parser = argparse.ArgumentParser(description="Grab contrail configs and compare with others. "
                                                 "Use for planned work verification and regular"
                                                 " checks on config sanity.")
    parser.add_argument("ips_file",
                        help="Location of YAML file containing Contrail component IPs")
    parser.add_argument("config_file",
                        help="Location of YAML file containing config file paths")
    parser.add_argument("-g", "--get-ips", action="store_true",
                        help="Generate ips_file from 'juju status'")
    parser.add_argument("-d", "--diff-only", action="store_true",
                        help="Only compare. Files must exist from previous runs'")
    parser.add_argument("-r", "--repo-name",
                        help="directory where files are stored in git, use"
                             " when regularly using script to track configs"
                             " over time. mutually exlusive with '-m'"
                             "directory is local to './repos/'")
    parser.add_argument("-m", "--maint-name",
                        help="directory where files are stored as plain text,"
                             "for comparision before and after a maintenance"
                             " mutually exlusive with '-r'"
                             "files are stored in './maintenances/'")
    parser.add_argument("-w", "--when",
                        help="use with '-m', indicate whether capture is 'before'"
                             "or 'after' the maintainance or if you want to 'diff"
                             "the files from previous captures")
    parser.add_argument("-u", "--username", default="ubuntu",
                        help="Username to SSH to contrail components. Default: 'ubuntu'")
    parser.add_argument("-p", "--inc-passwords", action="store_true",
                        help="Include passwords in the files grabbed")
    args = vars(parser.parse_args())
    if args['repo_name'] and args['maint_name']:
        print("please use only one of '-r' and '-m'")
        exit()
    elif not args['repo_name'] and not args['maint_name']:
        print("please specify one of '-r' and '-m'")
        exit()
    elif args['maint_name'] and not args['when']:
        print("please specify -w with 'before' or 'after")
        exit()
    return args


def main(args):
    """main script body"""
    if args['when'] == 'diff':
        file_dir = './maintenances/' + args['maint_name'] + '/'
        diff_files(file_dir + 'before', file_dir + 'after', 'normal')
        exit()
    LOGGER.info("getting juju status")
    juju_status = loop.run(get_juju_status_api())
    if args['get_ips']:
        LOGGER.info("generating and writing component IPs file from 'juju status' output")
        unit_ips = parse_juju_status_api(juju_status)
        write_file(yaml.dump(unit_ips, default_flow_style=False), args['ips_file'])
    unit_ips, conf_files = read_conf_files(args['ips_file'], args['config_file'])
    if args['maint_name']:
        output_dir = './maintenances/' + args['maint_name'] + '/' + args['when']
        check_dir(output_dir)
    elif args['repo_name']:
        output_dir = './repos/' + args['repo_name']
        check_dir_git(output_dir)
    write_file(get_juju_charm_versions(juju_status), output_dir + '/juju_apps.txt')
    write_config_files(unit_ips, conf_files,
                       output_dir, args['username'], args['inc_passwords']
                      )
    if args['maint_name'] and args['when'] == 'after':
        compare_dir = './maintenances/' + args['maint_name'] + '/before'
        diff_files(compare_dir, output_dir, 'normal')


if __name__ == '__main__':
    ARGS = cli_grab()
    if ARGS['maint_name']:
        MODE = 'maint'
    else:
        MODE = 'repo'
    LOGGER = logging_func(MODE)
    main(ARGS)

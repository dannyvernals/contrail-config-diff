""" Grab contrail config files and compare them against previous versions"""

import subprocess
import os
import shutil
import filecmp
import pathlib
import argparse
import re
import yaml


def get_juju_status():
    """get juju status from command line"""
    pipes = (subprocess.Popen(['juju', 'status'], stdout=subprocess.PIPE,  stderr=subprocess.PIPE))
    std_out, std_err = pipes.communicate(timeout=20)
    if pipes.returncode != 0:
        raise Exception(std_err.strip())
    return std_out.decode('utf-8')


def parse_juju_status(juju_status):
    """create a dict of contrail component IPs extracted from a 'juju status'"""
    unit_ips = {}
    juju_status = juju_status.split("\n")
    for line in juju_status:
        if line.startswith('  contrail-agent') and '/' in line:
            unit_ips.setdefault('contrail-agent', list()).append(str(line.split()[3]))
        elif line.startswith('contrail-controller/'):
            unit_ips.setdefault('contrail-controller', list()).append(str(line.split()[4]))
        elif line.startswith('contrail-analytics/'):
            unit_ips.setdefault('contrail-analytics', list()).append(str(line.split()[4]))
        elif line.startswith('contrail-analyticsdb/'):
            unit_ips.setdefault('contrail-analyticsdb', list()).append(str(line.split()[4]))
        elif line.startswith('contrail-haproxy/'):
            unit_ips.setdefault('contrail-haproxy', list()).append(str(line.split()[4]))
        elif line.startswith('heat/'):
            unit_ips.setdefault('heat', list()).append(str(line.split()[4]))
        elif line.startswith('neutron-api/'):
            unit_ips.setdefault('neutron', list()).append(str(line.split()[4]))
    return unit_ips

def read_file_lines(file_path):
    """get text from a file as list of lines"""
    with open(file_path) as file_handle:
        file_contents = file_handle.readlines()
    return file_contents


def read_file(file_path):
    """get text from a file"""
    with open(file_path) as fh:
        file_contents = fh.read()
    return file_contents

def read_conf_files(unit_ip_file, remote_files):
    """load settings from the specified yaml files"""
    conf_files = yaml.load(read_file(remote_files))
    unit_ips = yaml.load(read_file(unit_ip_file))
    return unit_ips, conf_files


def write_file(contents, file_location):
    """write arbitrary strings to a file"""
    with open(file_location, 'w+') as write_fh:
        write_fh.write(contents)
    os.chmod(file_location, 0o600)


def get_remote_file(remote_ip, file_location, username):
    """grab the text contents of a file on a remote system via SSH.
    as most contrail / openstack config files are only root readable
    do this via a sudo cat"""
    pipes = (subprocess.Popen(['ssh', username + '@{}'.format(remote_ip), 'sudo', 'cat', file_location],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE
                              )
            )
    std_out, std_err = pipes.communicate(timeout=20)
    if pipes.returncode != 0:
        if b'No such file or directory' in std_err:
            return ''
        raise Exception(std_err.strip())
    return std_out.decode('utf-8')


def password_wipe(text_blob):
    """remove passwords from text"""
    new_blob = []
    for line in text_blob.splitlines():
        if 'password' in line.lower() and 'auth_type' not in line.lower():
            line = re.split('=| ', line)
            new_blob.append(line[0] + ' #PASSWORD REMOVED#')
        else:
            new_blob.append(line)
    return '\n'.join(new_blob)


def write_config_files(unit_ips, files, dir_path, username, inc_passwords):
    """for components endpoints in 'unit_ips' grab config in 'files'
    and dump the file to 'dir'"""
    for component, server_ips in unit_ips.items():
        print("getting '{}' data".format(component))
        for server_ip in server_ips:
            print("from '{}'".format(server_ip))
            for conf_loc in files[component]:
                conf_file = get_remote_file(server_ip, conf_loc, username)
                if not inc_passwords:
                    conf_file = password_wipe(conf_file)
                file_name = conf_loc.replace('/', '_')
                pathlib.Path('{}/{}/{}'.format(dir_path, component, server_ip)).mkdir(parents=True, exist_ok=True)
                pathlib.Path('{}/{}/{}'.format(dir_path, component, server_ip)).chmod(0o700)
                write_file(str(conf_file), '{}/{}/{}/{}'.format(dir_path, component, server_ip, file_name))


def diff_files(old_dir, new_dir, diff_mode):
    """Instantiate a file compare object against the specified directories.
    call 'recurse_diff_files()' to compare all files in those directories"""
    dcmp = filecmp.dircmp(old_dir, new_dir)
    recurse_diff_files(dcmp, diff_mode)


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
        #print((dcmp.left, dcmp.right, dcmp.diff_files))
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


def cli_grab():
    """take stuff from cli, output it in a dict"""
    parser = argparse.ArgumentParser(description="Grab contrail configs and compare with others. "
                                                 "Use for planned work verification.")
    parser.add_argument("ips_file", help="Location of YAML file containing Contrail component IPs")
    parser.add_argument("config_file", help="Location of YAML file containing config file paths")
    parser.add_argument("output_dir", help="Location of where to store config files")
    parser.add_argument("compare_dir", help="Location of config files to compare against")
    parser.add_argument("-g", "--get-ips", action="store_true", help="Generate ips_file from 'juju status'")
    parser.add_argument("-f", "--get-ips-file", help="Generate ips_file from 'juju status' "
                                                     "output previously saved to a file")
    parser.add_argument("-d", "--diff-only", action="store_true", help="Only compare files. They must "
                                                                       "exist from previous runs'")
    parser.add_argument("-m", "--diff-mode", default="normal", help="Style of diff. "
                                                                    "'normal', 'context' or 'unified'")
    parser.add_argument("-u", "--username", default="ubuntu", help="Username to SSH to contrail components. "
                                                                   "Default is 'ubuntu'")
    parser.add_argument("-p", "--inc-passwords", action="store_true", help="Include passwords in the files grabbed")
    args = vars(parser.parse_args())
    return args


def check_dir(output_dir):
    """warn if output dir already exists, delete it if user accepts this"""
    if os.path.dirname(os.path.realpath(__file__)) == os.path.realpath(output_dir):
        print("you have specified an output dir that is where the script runs, please use a sub directory")
        exit()
    if os.path.exists(output_dir):
        while True:
            answer = input("output directory already exists, old files will be deleted, proceed?, y/n:")
            if answer.lower() not in ('y', 'n'):
                print("'y' or 'n' only please")
            else:
                break
            if answer.lower() == 'n':
                exit()
            elif answer.lower() == 'y':
                continue
        shutil.rmtree(output_dir)
    os.mkdir(output_dir)


def main():
    """main script body"""
    args = cli_grab()
    if args['get_ips']:
        print("getting juju status")
        status = get_juju_status()
        print("generating and writing component IPs file from 'juju status' output")
        unit_ips = parse_juju_status(status)
        write_file(yaml.dump(unit_ips, default_flow_style=False), args['ips_file'])
    elif args['get_ips_file']:
        status = read_file(args['get_ips_file'])
        unit_ips = parse_juju_status(status)
        write_file(yaml.dump(unit_ips, default_flow_style=False), args['ips_file'])
    unit_ips, conf_files = read_conf_files(args['ips_file'], args['config_file'])
    if not args['diff_only']:
        check_dir(args['output_dir'])
        write_config_files(unit_ips, conf_files, args['output_dir'], args['username'], args['inc_passwords'])
    diff_files(args['compare_dir'], args['output_dir'], args['diff_mode'])


if __name__ == '__main__':
    main()
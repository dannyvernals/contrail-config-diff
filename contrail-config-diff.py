import subprocess
import yaml
import filecmp
import pathlib
import difflib
import argparse



def get_juju_status():
    """get juju status from command line"""
    pipes = (subprocess.Popen(['juju', 'status'], stdout=subprocess.PIPE,  stderr=subprocess.PIPE))
    std_out, std_err = pipes.communicate()
    if pipes.returncode != 0:
        raise Exception(std_err.strip())
    else:
        return std_out.decode('utf-8')


def parse_juju_status(juju_status):
    """create a dict of contrail component IPs extracted from a 'juju status'"""
    unit_ips = {}
    juju_status = juju_status.split("\n")
    for line in juju_status:
        if 'contrail-agent/' in line:
            unit_ips.setdefault('contrail-agent', list()).append(str(line.split()[3]))
        elif "contrail-controller/" in line:
            unit_ips.setdefault('contrail-controller', list()).append(str(line.split()[4]))
        elif "contrail-analytics/" in line:
            unit_ips.setdefault('contrail-analytics', list()).append(str(line.split()[4]))
        elif "contrail-analyticsdb/" in line:
            unit_ips.setdefault('contrail-analyticsdb', list()).append(str(line.split()[4]))
        elif "contrail-haproxy/" in line:
            unit_ips.setdefault('contrail-haproxy', list()).append(str(line.split()[4]))
        elif "heat/" in line:
            unit_ips.setdefault('heat', list()).append(str(line.split()[4]))
        elif "neutron-api/" in line:
            unit_ips.setdefault('neutron', list()).append(str(line.split()[4]))
    return unit_ips


def read_conf_files(unit_ip_file, remote_files):
    """load settings from the specified yaml files"""
    with open (remote_files, 'r') as conf_fh:
        conf_files = yaml.load(conf_fh.read())
    with open (unit_ip_file, 'r') as units_fh:
        unit_ips = yaml.load(units_fh.read())
    return unit_ips, conf_files


def write_file(contents, file_location):
    """write arbitrary strings to a file"""
    with open(file_location, 'w') as write_fh:
        write_fh.write(contents)


def get_remote_file(remote_ip, file_location):
    """grab the text contents of a file on a remote system via SSH.
    as most contrail / openstack config files are only root readable
    do this via a sudo cat"""
    pipes = (subprocess.Popen(['ssh', 'ubuntu@{}'.format(remote_ip), 'sudo', 'cat', file_location],
                 stdout=subprocess.PIPE,  stderr=subprocess.PIPE))
    std_out, std_err = pipes.communicate()
    if pipes.returncode != 0:
        if b'No such file or directory' in std_err:
            return ''
        else:
            raise Exception(std_err.strip())
    return std_out.decode('utf-8')


def write_config_files(unit_ips, files, dir):
    """for components endpoints in 'unit_ips' grab config in 'files'
    and dump the file to 'dir'"""
    for component, server_ips in unit_ips.items():
        print("getting *{}* data".format(component))
        for server_ip in server_ips:
            print("from *{}*".format(server_ip))
            for conf_loc in files[component]:
                conf_file = get_remote_file(server_ip, conf_loc)
                file_name = conf_loc.replace('/', '_')
                pathlib.Path('{}/{}/{}'.format(dir, component, server_ip)).mkdir(parents=True, exist_ok=True)
                write_file(str(conf_file), '{}/{}/{}/{}'.format(dir, component, server_ip, file_name))


def read_file(file_path):
    with open(file_path) as fh:
        file_contents = fh.readlines()
    return file_contents


def diff_files(old_dir, new_dir):
    """Instantiate a file compare object against the specified directories."""
    dcmp = filecmp.dircmp(old_dir, new_dir)
    recurse_diff_files(dcmp)


def recurse_diff_files(dcmp):
    """Recurse through all subdirs of 'dcmp' dircmp object
    Return all the files missing and print a diff of all files that are different"""
    if dcmp.diff_files:
        for file_name in dcmp.diff_files:
            left_file = dcmp.left + '/' + file_name
            right_file = dcmp.right + '/' + file_name
            left_lines = read_file(left_file)
            right_lines = read_file(right_file)
            print('=' * 100)
            for line in difflib.unified_diff(left_lines, right_lines, fromfile=left_file, tofile=right_file, lineterm=''):
                print(line)
        #print((dcmp.left, dcmp.right, dcmp.diff_files))
    if dcmp.left_only:
        print('=' * 100)
        print("Files missing in the '{}' directory: ".format(dcmp.left))
        print('\n'.join(dcmp.left_only))
    if dcmp.right_only:
        print('=' * 100)
        print("Files missing in the '{}' directory: ".format(dcmp.right))
        print('\n'.join(dcmp.right_only))    
    for sub_dcmp in dcmp.subdirs.values():
        recurse_diff_files(sub_dcmp)


def cli_grab():
    """take stuff from cli, output it in a dict"""
    parser = argparse.ArgumentParser(description="Grab contrail configs and compare against others. "
                                                 "Use for planned work verification.")
    parser.add_argument("ips_file", help="Location of YAML file containing Contrail component IPs")
    parser.add_argument("config_file", help="Location of YAML file containing config file paths")
    parser.add_argument("output_dir", help="Location of where to store config files")
    parser.add_argument("compare_dir", help="Location of config files to compare against")
    parser.add_argument("-g", "--get-ips", action="store_true", help="Generate the ips_file from 'juju status'")
    args = vars(parser.parse_args())
    return args



def main():
    args = cli_grab()
    if args['get_ips']:
        print("getting juju status")
        status = get_juju_status()
        print("generating and writing component IPs file from 'juju status' output")
        unit_ips = parse_juju_status(status)
        write_file(yaml.dump(unit_ips, default_flow_style=False), args['ips_file'])
    unit_ips, conf_files = read_conf_files(args['ips_file'], args['config_file'])
    #write_config_files(unit_ips, conf_files, args['output_dir'])
    diff_files(args['compare_dir'], args['output_dir'])

if __name__ == '__main__':
    main()
"""
rmapi.py

Utility functions to call rmapi.
"""
import subprocess
import os
import re

class RMAPI(object):
    def __init__(self, rmapi_path, verbose=False):
        self.rmapi_path = rmapi_path
        self.verbose = verbose

    def __call__(self, cmd, *args,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        '''
        Run the rmapi on a given command, returning the status code.
        '''
        sub_args = [self.rmapi_path, cmd] + [a for a in args]
        return subprocess.call(sub_args, stdout=stdout, stderr=stderr)

    def run(self, cmd, *args):
        '''
        Run the rmapi on a given command, returning stdout if no error,
        otherwise returns stderr.
        '''
        sub_args = [self.rmapi_path, cmd] + [a for a in args]
        result = subprocess.run(sub_args, capture_output=True)
        if result.returncode == 0:
            return result.stdout
        else:
            return result.stderr

    def checkdir(self, dir):
        '''
        Check if a given directory exists.

        Args:
        -----
        dir : str or list
            Either a directory string or hierarchy.
        '''
        if isinstance(dir, list):
            dir = '/'.join(dir)
        result = subprocess.call([self.rmapi_path, "find", dir],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        return not bool(result)

    def checkfile(self, path):
        '''
        Checks if a given path exists, stripping extension.
        '''
        path = os.path.splitext(path)[0]
        result = self("find", path)
        return not bool(result)

    def mkdir(self, dir):
        '''
        Make a directory recursively, if it does not exist.

        Args:
        -----
        dir : str or list
            Either a directory string or hierarchy.
        '''
        if isinstance(dir, list):
            hierarchy = dir
        else:
            hierarchy = dir.split('/')

        dirstr = ""
        direxists = True
        for folder in hierarchy:
            dirstr += "/" + folder
            if len(dirstr) < 2:
                break
            # Check if directory exists if parent existed.
            if direxists:
                direxists = self.checkdir(dirstr)

            # Create directory if it doesn't exist.
            if not direxists:
                status = self("mkdir", dirstr)
                if status != 0:
                    raise Exception("Could not create directory "
                                    + dirstr + " on remarkable.")
                if self.verbose:
                    print("\tCreated directory {:s} on remarkable".format(dirstr))

        if direxists and self.verbose:
            print("\tDirectory {:s} already on remarkable".format(dirstr))

        return dirstr

    def stat(self, path):
        '''
        Run the stat command, returning the results as a dict
        '''
        path = os.path.splitext(path)[0]
        result = subprocess.run([self.rmapi_path, 'stat', path],
                                capture_output=True)

        if result.returncode != 0:
            raise Exception("Could not run stat, error: \n{:s}".format(result.stderr.decode('ascii')))

        stat_res_str = result.stdout.split(b'\n')[1].decode('ascii')

        stat_regex = re.compile('[{|\s](\w+):(\S*)(?=[\s|}])')
        match = stat_regex.findall(stat_res_str)
        if len(match) < 1:
            raise Exception("Could not parse result from stat: \n{:s}")

        stat_dict = {}
        for m in match:
            stat_dict[m[0]] = m[1]

        return stat_dict

    def get(self, path, dir=None):
        '''
        Run the get command, obtaining the desired file into the desired directory.

        Returns
        -------
        path to returned zip file
        '''
        path = os.path.splitext(path)[0]
        result = subprocess.run([self.rmapi_path, 'get', path],
                                capture_output=True, cwd=dir)

        if result.returncode != 0:
            raise Exception("Could not run get, error: \n{:s}".format(result.stderr.decode('ascii')))

        filename = os.path.basename(path)
        if dir is None:
            dir = os.getcwd()
        return os.path.join(dir, filename + '.zip')

    def put(self, attachment, dir="/"):
        '''
        Run the put command, uploading a file to reMarkable.

        Returns
        -------
        status code
        '''
        status = self("put", attachment, dir)
        if status != 0:
            raise Exception("Could not upload file " + attachment + " to remarkable.")

        return status



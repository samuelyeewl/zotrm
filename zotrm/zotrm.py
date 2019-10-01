"""
zotrm.py

Send Zotero papers to ReMarkable tablet.

@author Samuel Yee
"""
import os
import configparser
import glob
import re
import argparse
import subprocess
from pyzotero import zotero

def main(verbose=False):
    # Read configuration file
    config = configparser.ConfigParser()
    config_file = os.path.expanduser('~/.zotrm/config.ini')
    if not os.path.exists(config_file):
        print("Configuration file not found, exiting.")
        return -1
    config.read(config_file)
    zot_lib_id = config['Zotero']['LIBRARY_ID']
    zot_api_key = config['Zotero']['API_KEY']
    zot_storage_dir = os.path.expandvars(config['Zotero']['STORAGE_DIR'])
    zot_send_tag = config['Zotero']['SEND_TAG']
    zot_replace = 'REPLACE_TAG' in config['Zotero']
    if zot_replace:
        zot_replace_tag = config['Zotero']['REPLACE_TAG']
    rmapi_path = os.path.expandvars(config['RMAPI']['RMAPI_PATH'])
    rm_base_dir = config['Remarkable']['BASE_DIR']
    rm_default_dir = config['Remarkable']['DEFAULT_DIR']

    # Get list of pdfs
    pdflist = glob.glob(os.path.join(zot_storage_dir, '*/*.pdf'))

    zot = zotero.Zotero(zot_lib_id, 'user', zot_api_key)
    z = zot.top(tag=zot_send_tag)
    if verbose:
        print("Found {:d} papers to send...".format(len(z)))

    for paper in z:
        try:
            # Search for relevant PDF
            lastname = paper['data']['creators'][0]['lastName']
            yr = paper['meta']['parsedDate'].split('-')[0]
            full_title = paper['data']['title']
            title = full_title[:20]
            # Escape special characters
            esc_title = re.escape(title)
            searchstr = '{0:s}[_\s].*{1:s}_{2:s}'.format(lastname, yr, esc_title)
            r = re.compile(os.path.join(zot_storage_dir,
                                        '[A-Z0-9]*/' + searchstr))
            foundfiles = list(filter(r.match, pdflist))
            if len(foundfiles) < 1:
                print("Could not find {:s}".format(searchstr))
                continue
            foundfile = foundfiles[0]
        except:
            raise
        pdfname = os.path.basename(foundfile)

        # Get collection(s)
        collections = paper['data']['collections']
        if len(collections) < 1:
            # If not in a collection, use default dir
            hierarchy = [rm_default_dir]
        else:
            hierarchy = []
            coll = collections[0]
            coll_info = zot.collection(coll)
            hierarchy.append(coll_info['data']['name'])
            # Get full hierarchy
            while coll_info['data']['parentCollection']:
                coll = coll_info['data']['parentCollection']
                coll_info = zot.collection(coll)
                hierarchy.append(coll_info['data']['name'])
            hierarchy.reverse()

        if verbose:
            print("Found PDF file {:s}".format(pdfname))

        # Remove tag
        paper['data']['tags'] = [tag for tag in paper['data']['tags']
                                 if tag['tag'] != zot_send_tag]
        if zot_replace:
            paper['data']['tags'].append({'tag': zot_replace_tag})
        # Update item
        zot.update_item(paper)
        if verbose:
            print("Updated tags for {:s}".format(full_title))

        # Upload to remarkable
        dirstr = ""
        direxists = True
        try:
            # Create folders
            for folder in hierarchy:
                dirstr += "/" + folder
                if len(dirstr) < 2:
                    break
                # Check if directory exists if parent existed.
                if direxists:
                    direxists = not subprocess.call([rmapi_path, "find", dirstr],
                                                    stdout=subprocess.DEVNULL,
                                                    stderr=subprocess.DEVNULL)
                # Create directory if it doesn't exist.
                if not direxists:
                    status = subprocess.call([rmapi_path, "mkdir", dirstr],
                                             stdout=subprocess.DEVNULL)
                    if status != 0:
                        raise Exception("Could not create directory "
                                        + dirstr + " on remarkable.")
                    if verbose:
                        print("Created directory " + dirstr
                              + " on remarkable.")

            # Upload PDF
            fileexists = not subprocess.call([rmapi_path, "find", dirstr + "/" +
                                              os.path.splitext(pdfname)[0]],
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
            if fileexists:
                if verbose:
                    print("File {:s} already exists, skipping...".format(pdfname))
                continue
            status = subprocess.call([rmapi_path, "put", foundfile, dirstr],
                                     stdout=subprocess.DEVNULL)
            if status != 0:
                raise Exception("Could not upload file " + foundfile +
                                " to remarkable.")
            if verbose:
                print("Uploaded " + pdfname + ".")

        except Exception as err:
            print(err)
            continue


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Send papers from Zotero to ReMarkable tablet.")
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    main(args.verbose)

"""
zotrm.py

Send Zotero papers to ReMarkable tablet.

@authors Samuel Yee, @github/narroo
"""
import os
import configparser
import glob
import re
import argparse
import subprocess
from pyzotero import zotero
import landscape_pdf

def read_config():
    '''
    Read the configuration file and return a dictionary of parameters.
    '''
    config = configparser.ConfigParser()
    config_file = os.path.expanduser('~/.zotrm/config.ini')
    if not os.path.exists(config_file):
        print("Configuration file not found, exiting.")
        return -1
    config.read(config_file)

    d = {}
    d['zot_lib_id'] = config['Zotero']['LIBRARY_ID']
    d['zot_api_key'] = config['Zotero']['API_KEY']
    d['zot_storage_dir'] = os.path.expandvars(config['Zotero']['STORAGE_DIR'])
    if 'ATTACHMENT_DIR' in config['Zotero']:
        d['zot_attachment_dir'] = os.path.expandvars(config['Zotero']['ATTACHMENT_DIR'])
    d['zot_send_tag'] = config['Zotero']['SEND_TAG']
    d['zot_replace'] = 'REPLACE_TAG' in config['Zotero']
    if d['zot_replace']:
        d['zot_replace_tag'] = config['Zotero']['REPLACE_TAG']
    d['rmapi_path'] = os.path.expandvars(config['RMAPI']['RMAPI_PATH'])
    if 'BASE_DIR' in config['Remarkable']:
        d['rm_base_dir'] = config['Remarkable']['BASE_DIR']
    d['rm_default_dir'] = config['Remarkable']['DEFAULT_DIR']

    return d

def get_attachment(papers, zot, config):
    '''
    Get the PDF attachment for the given paper.

    Args:
    -----
    paper : list of dict
        Item to get attachment for
    zot : pyzotero.zotero.Zotero
        Zotero library.

    Returns:
    --------
    list of filenames
    '''

    return attachments


def main(verbose=False, landscape=False):
    # Read configuration file
    config = read_config()
    rmapi_path = config['rmapi_path']
    zot = zotero.Zotero(config['zot_lib_id'], 'user', config['zot_api_key'])

    # Get list of papers with the appropriate tag
    z = zot.top(tag=config['zot_send_tag'])

    if verbose:
        print("Found {:d} papers to send...".format(len(z)))

    # Get list of files in Zotero storage dir
    pdflist = glob.glob(os.path.join(config['zot_storage_dir'], '*/*.pdf'))
    if pdflist == '':
        print("No PDF files found.")
        return

    for paper in z:
        if verbose:
            print("Preparing paper {:s}".format(paper['data']['title']))

        # Find PDF
        attachments = []

        # Recursively search for attachments
        queue = [paper]
        while queue:
            item = queue.pop()
            if item['data']['itemType'] != 'attachment':
                # Note items don't have children to look through
                if item['data']['itemType'] != 'note':
                    queue += zot.children(item['key'])
                continue
            # Get filename
            if 'filename' in item['data']:
                filename = item['data']['filename']
            elif 'path' in item['data']:
                filename = item['data']['path']
            else:
                # No file found in this attachment
                continue

            # Make sure file is a PDF
            if '.pdf' not in filename.casefold():
                continue
            # Join base file name
            if filename.startswith('attachments:'):
                # For linked attachments, we have the whole filename already.
                filename = filename[12:]
                if 'zot_attachment_dir' not in config:
                    print("ERR: No attachment directory provided in config file.")
                    continue
                filename = os.path.join(config['zot_attachment_dir'], filename)
                if os.path.exists(filename):
                    attachments.append(filename)
            else:
                # Without linked attachments, PDF is in some subdirectory.
                dirname = re.escape(config['zot_storage_dir'])
                regexfilename = re.escape(filename)
                regexfilename = os.path.join(dirname, '[A-Z0-9]*/' + regexfilename)
                r = re.compile(regexfilename)
                # Match files to list
                foundfiles = list(filter(r.match, pdflist))
                if len(foundfiles) < 1 :
                    print("ERR: Cannot find file \"{:s}\" in storage directory \"{:s}\", skipping...".format(filename,dirname))
                    continue
                else:
                    for f in foundfiles:
                        if os.path.exists(f):
                            attachments.append(f)

        # If no attachments were found, skip the upload
        if not attachments:
            print("\tNo attachments found, skipping upload")
            continue

        if verbose:
            for f in attachments:
                print("\tFound PDF attachment {:s}".format(os.path.basename(f)))

        # Get collection(s)
        collections = paper['data']['collections']
        if len(collections) < 1:
            # If not in a collection, use default dir
            hierarchy = [config['rm_default_dir']]
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
            if 'rm_base_dir' in config and config['rm_base_dir'] != "/":
                hierarchy.append(config['rm_base_dir'])
            hierarchy.reverse()

        if verbose:
            print("\tPlacing attachments in folder {:s}".format('/'.join(hierarchy)))

        # Upload to remarkable
        dirstr = ""
        direxists = True
        try:
            # Create folders recursively
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
                        print("\tCreated directory {:s} on remarkable".format(dirstr))

            # Upload PDF
            for attachment in attachments:
                pdfname = os.path.basename(attachment)
                if landscape:
                    landscape_file = os.path.join('/tmp', pdfname.replace('.pdf', '_landscape.pdf'))
                    if verbose:
                        print("\tConverting file {:s} to landscape mode and saving at {:s}".format(attachment, landscape_file))
                    landscape_pdf.convert_to_landscape(attachment, landscape_file)
                    attachment = landscape_file
                    pdfname = os.path.basename(attachment)
                    if verbose:
                        print("\tDone")

                fileexists = not subprocess.call([rmapi_path, "find", dirstr + "/" +
                                                  os.path.splitext(pdfname)[0]],
                                                 stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL)
                if fileexists:
                    if verbose:
                        print("\tFile {:s} already exists, skipping...".format(pdfname))
                    continue
                status = subprocess.call([rmapi_path, "put", attachment, dirstr],
                                         stdout=subprocess.DEVNULL)
                if status != 0:
                    raise Exception("\tCould not upload file " + pdfname +
                                    " to remarkable.")
                if verbose:
                    print("\tUploaded {:s}.".format(pdfname))

        except Exception as err:
            print(err)
            continue

        # Remove tag
        paper['data']['tags'] = [tag for tag in paper['data']['tags']
                                 if tag['tag'] != config['zot_send_tag']]
        if config['zot_replace']:
            paper['data']['tags'].append({'tag': config['zot_replace_tag']})
        # Update item
        zot.update_item(paper)
        if verbose:
            print("\tUpdated tags.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Send papers from Zotero to ReMarkable tablet.")
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--landscape', '-l', action='store_true')
    args = parser.parse_args()

    main(args.verbose, args.landscape)


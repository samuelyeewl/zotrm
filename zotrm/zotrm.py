"""
zotrm.py

Send Zotero papers to ReMarkable tablet.

@authors Samuel Yee, @github/narroo
"""
import os, shutil
import configparser
import glob
import re
import argparse
import subprocess
from pyzotero import zotero
import landscape_pdf
import rmapi
import datetime
import json
import markdown


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
    if 'remarks' in config and 'REMARKS_PATH' in config['remarks']:
        d['remarks_path'] = config['remarks']['REMARKS_PATH']

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


def get_collection_hierarchy(paper, zot, config):
    '''
    Get collection hierarchy for a given paper.

    Args:
    -----
    paper : dict
        pyzotero dict
    zot : zotero.Zotero
        zotero object
    config : dict
        configuration dictionary
    '''
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

    return hierarchy


def get_pdf_attachments(paper, zot, config, return_zot_dict=False):
    '''
    Get a list of PDF attachments for the given paper.
    '''
    # Recursively search for attachments
    queue = [paper]
    attachments = []
    while queue:
        item = queue.pop()
        # Search for attachments
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
        # Ignore _remarks output
        elif filename.endswith('_remarks.pdf'):
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
                if return_zot_dict:
                    attachments.append((filename, item))
                else:
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
                    if not os.path.exists(f):
                        continue
                    if return_zot_dict:
                        attachments.append((f, item))
                    else:
                        attachments.append(f)

    return attachments


def add_md_to_paper(paper, md_file, zot, verbose=False):
    '''
    Add a markdown file as a zotero note to a paper.

    Returns
    -------
    zotero response
    '''
    # Read in file
    if verbose:
        print("Reading in .md file...")
    with open(md_file, 'r') as f:
        md_str = markdown.markdown(f.read())
    md_str = '<p id="title"><strong>Extracted highlights</strong></p>\n' + md_str

    # Create note
    if verbose:
        print("Creating note...")
    note = zot.item_template('note')
    note['note'] = md_str
    note['parentItem'] = paper['key']
    if verbose:
        print("Uploading note...")
    res = zot.create_items([note])

    if '0' not in res['success']:
        raise Exception("Failed to upload note to Zotero", res)

    return res

def add_pdf_to_paper(attachment, pdf_file, zot, config, verbose=False):
    '''
    Add an annotated PDF to the paper
    '''
    # We follow the link mode of the original attachment
    link_mode = attachment['data']['linkMode']
    if link_mode == "imported_file":
        # For imported files, we simply upload the file directly
        res = zot.attachment_simple(pdf_file, attachment['data']['parentItem'])
    elif link_mode == "linked_file":
        # For linked files, we create the item directly
        if verbose:
            print("Creating new attachment...")
        new_attachment = zot.item_template('attachment', 'linked_file')
        new_attachment['title'] = os.path.basename(pdf_file)
        new_attachment['parentItem'] = attachment['data']['parentItem']
        new_attachment['contentType'] = 'application/pdf'

        # Get attachment location
        attachment_fn = attachment['data']['path']
        if not attachment_fn.startswith('attachments:'):
            raise Exception("Invalid filename for linked attachment: {:s}".format(attachment_fn))
        attachment_fn = attachment_fn[12:]
        attachment_dir, basename = os.path.split(attachment_fn)
        # Get full attachment directory
        attachment_dir = os.path.join(config['zot_attachment_dir'], attachment_dir)

        # Move file to appropriate destination
        out_pdf_file = os.path.join(attachment_dir, basename.replace('.pdf', ' _remarks.pdf'))
        if verbose:
            print("Moving pdf file to {:s}".format(out_pdf_file))
        shutil.move(pdf_file, out_pdf_file)

        # Add attachment path to metadata
        new_attachment['path'] = attachment['data']['path'].replace('.pdf', ' _remarks.pdf')

        # Upload attachment
        if verbose:
            print("Uploading attachment...")
        res = zot.create_items([new_attachment], attachment['data']['parentItem'])
    else:
        raise Exception("Invalid linkMode {:s}".format(link_mode))

    if '0' not in res['success']:
        raise Exception("Failed to upload pdf to Zotero", res)

    return res

def extract_remarks(path, rmapi, config, outdir='./', metadata=None,
                    targets=['md', 'pdf'], verbose=False):
    '''
    Use the remarks script to extract an annotated file from remarkable

    Note: Uses the modified remarks script.
    '''
    # First, get the file off reMarkable
    dir = os.path.expanduser('~/.zotrm/')
    basename = os.path.splitext(os.path.basename(path))[0]
    outzip = rmapi.get(path, dir=dir)
    if metadata is None:
        metadata = rmapi.stat(path)

    # Create temporary dir
    temp_dir = os.path.join(dir, basename + '/')
    # Overwrite existing comments if necessary
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.mkdir(temp_dir)
    if verbose:
        print("Making directory {:s}".format(temp_dir))

    # Unzip
    if verbose:
        print("Unzipping results...")

    res = subprocess.run(['unzip', outzip, '-d', temp_dir],
                         capture_output=True)
    if res.returncode != 0:
        raise Exception("Could not unzip file {:s}".format(outzip))

    # Remarks requires a metadata file
    metadata_fn = os.path.join(temp_dir, metadata['ID'] + '.metadata')
    min_metadata = {
        "type": metadata['Type'],
        "path": metadata['ID'],
        "visibleName": metadata['VissibleName'],
        "parent": ""
    }
    if verbose:
        print("Creating metadata file...")
    with open(metadata_fn, 'w') as f:
        f.write(json.dumps(min_metadata))

    # Create output directory for annotations
    annotate_dir = os.path.join(temp_dir, 'annotated/')
    os.mkdir(annotate_dir)

    # Run remarks
    remarks_cmd = "cd {:s} && ".format(config['remarks_path'])
    remarks_cmd += "python -m remarks "
    remarks_cmd += "'{:s}' '{:s}' ".format(temp_dir, annotate_dir)
    remarks_cmd += "--targets " + " ".join(targets) + " "
    if "md" in targets:
        remarks_cmd += "--combined_md "
    if "pdf" in targets:
        remarks_cmd += "--combined_pdf "
    if verbose:
        print("Running remarks to extract annotations...: \n{:s}".format(remarks_cmd))
    res = subprocess.run(remarks_cmd, shell=True, capture_output=True)

    if res.returncode != 0:
        raise Exception("Could not run remarks, error {:s}".format(result.stderr))

    # Move files to output dir
    if verbose:
        print("Moving file to output directory...")
    out_fns = []
    remarks_basename = min_metadata['visibleName']
    if "md" in targets:
        md_fn = os.path.join(annotate_dir, remarks_basename + '.md')
        out_md_fn = os.path.join(outdir, basename + '.md')
        shutil.move(md_fn, out_md_fn)
        out_fns.append(out_md_fn)
    if "pdf" in targets:
        pdf_fn = os.path.join(annotate_dir, remarks_basename + ' _remarks.pdf')
        out_pdf_fn = os.path.join(outdir, basename + ' _remarks.pdf')
        shutil.move(pdf_fn, out_pdf_fn)
        out_fns.append(out_pdf_fn)

    return out_fns


def backsync_papers(zot, rmapi, config, verbose=False):
    '''
    Backsync papers onto computer.
    '''
    # Get list of papers from Zotero that are on the remarkable
    z = zot.top(tag=config['zot_replace_tag'])
    if verbose:
        print("Checking {:d} files on reMarkable".format(len(z)))

    for paper in z:
        # Get list of attachments
        attachments = get_pdf_attachments(paper, zot, config, return_zot_dict=True)
        rm_hierarchy = get_collection_hierarchy(paper, zot, config)

        for (attachment, zot_attach) in attachments:
            # Check to see if file is on remarkable
            basename = os.path.basename(attachment)
            # Full path on remarkable
            rm_path = "/".join(rm_hierarchy) + "/" + basename
            on_rm = rmapi.checkfile(rm_path)
            if verbose and on_rm:
                print("Found {:s} on reMarkable".format(rm_path))
            elif not on_rm:
                print("Could not find {:s} on reMarkable, skipping...".format(rm_path))
                continue

            # Check last modification date on reMarkable
            attachment_metadata = rmapi.stat(rm_path)
            last_modified_str = attachment_metadata['ModifiedClient']
            # The UTC+0 timezone is sometimes denoted as Z, but this is
            # not recognized by datetime:
            # https://discuss.python.org/t/parse-z-timezone-suffix-in-datetime/2220/14
            last_modified_str = last_modified_str.replace('Z', '+00:00')
            rm_last_modified = datetime.datetime.fromisoformat(last_modified_str)

            # Check to see if annotated file exists in zotero
            zot_remarks_attachment = attachment.replace('.pdf', ' _remarks.pdf')
            if os.path.exists(zot_remarks_attachment):
                # Check last modified date
                remarks_last_modified = datetime.datetime.utcfromtimestamp(
                    os.path.getmtime(zot_remarks_attachment))
                # Set UTC timezone for comparison
                remarks_last_modified = remarks_last_modified.replace(
                    tzinfo=datetime.timezone.utc)
                # If file on computer is newer than on remarkable, skip this file.
                if remarks_last_modified > rm_last_modified:
                    if verbose:
                        print("File on reMarkable is older than computer, skipping...")
                    continue

            # If there is no current annotated file or the file on the computer
            # is outdated, then we should get the annotated file.

            # Use remarks to extract PDF and MD
            annotated_files = extract_remarks(rm_path, rmapi, config,
                                              metadata=attachment_metadata,
                                              verbose=verbose, targets=['md', 'pdf'])

            # Add extracted files to zotero notes
            if verbose:
                print("Adding extracted highlights to zotero...")
            md_res = add_md_to_paper(paper, annotated_files[0], zot,
                                     verbose=verbose)
            pdf_res = add_pdf_to_paper(zot_attach, annotated_files[1], zot, config,
                                       verbose=verbose)
            return


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
        attachments = get_pdf_attachments(paper, zot, config)

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


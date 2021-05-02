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
from rmapi import RMAPI
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
    pdflist = None

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
            if pdflist is None:
                pdflist = glob.glob(os.path.join(dirname, '*/*.pdf'))

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
        print("\t\tReading in .md file...")
    with open(md_file, 'r') as f:
        md_str = markdown.markdown(f.read())
    # Remove default header
    md_str = re.sub('<h1>.*</h1>\n', '', md_str)
    # Add extracted highlights header
    md_str = '<p id="title"><strong>Extracted highlights</strong></p>\n' + md_str

    # Create note
    if verbose:
        print("\t\tCreating note...")
    note = zot.item_template('note')
    note['note'] = md_str
    note['parentItem'] = paper['key']
    if verbose:
        print("\t\tUploading note...")
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
            print("\t\tCreating new attachment...")
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
            print("\t\tMoving pdf file to {:s}".format(out_pdf_file))
        shutil.move(pdf_file, out_pdf_file)

        # Add attachment path to metadata
        new_attachment['path'] = attachment['data']['path'].replace('.pdf', ' _remarks.pdf')

        # Upload attachment
        if verbose:
            print("\t\tUploading attachment...")
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
        print("\t\tMaking temp directory {:s}".format(temp_dir))

    # Unzip
    if verbose:
        print("\t\tUnzipping results.")

    res = subprocess.run(['unzip', outzip, '-d', temp_dir],
                         capture_output=True)
    if res.returncode != 0:
        raise Exception("Could not unzip file {:s}".format(outzip))

    # Remove zip file
    if verbose:
        print("\t\tRemoving zip file.")
    os.remove(outzip)

    # Remarks requires a metadata file
    metadata_fn = os.path.join(temp_dir, metadata['ID'] + '.metadata')
    min_metadata = {
        "type": metadata['Type'],
        "path": metadata['ID'],
        "visibleName": metadata['VissibleName'],
        "parent": ""
    }
    if verbose:
        print("\t\tCreating metadata file...")
    with open(metadata_fn, 'w') as f:
        f.write(json.dumps(min_metadata))

    # Create output directory for annotations
    annotate_dir = os.path.join(temp_dir, 'annotated/')
    os.mkdir(annotate_dir)

    # Run remarks
    remarks_cmd = "cd {:s} && ".format(config['remarks_path'])
    remarks_cmd += "python -m remarks "
    remarks_cmd += "'{:s}' '{:s}' ".format(temp_dir, annotate_dir)
    remarks_cmd += "-f "
    remarks_cmd += "--targets " + " ".join(targets) + " "
    if "md" in targets:
        remarks_cmd += "--combined_md --md_page_numbers "
    if "pdf" in targets:
        remarks_cmd += "--combined_pdf "
    if verbose:
        print("\t\tRunning remarks to extract annotations...: \n\t\t{:s}".format(remarks_cmd))
    res = subprocess.run(remarks_cmd, shell=True, capture_output=True, text=True)

    if res.returncode != 0:
        raise Exception("Could not run remarks, error {:s}".format(res.stderr))

    if "No annotations found" in res.stdout:
        print("\t\tNo annotations found.")
        out_fns = []
    else:
        # Move files to output dir
        if verbose:
            print("\t\tMoving file to output directory...")
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

    # Remove temporary directory
    if verbose:
        print("\t\tRemoving temp directory {:s}".format(temp_dir))
    shutil.rmtree(temp_dir)

    return out_fns


def backsync_papers(zot, rmapi, config, verbose=False, dry_run=False,
                    exclude=[]):
    '''
    Backsync papers onto computer.
    '''
    # Get list of papers from Zotero that are on the remarkable
    z = zot.top(tag=config['zot_replace_tag'])
    if verbose:
        print("Checking {:d} files on reMarkable.".format(len(z)))

    exclude_keys = [p['key'] for p in exclude]

    for paper in z:
        if paper['key'] in exclude_keys:
            if verbose:
                print("Skipping paper {:s}, just sent.".format(paper['data']['title']))
            continue

        if verbose:
            print("Preparing paper {:s}".format(paper['data']['title']))

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
                print("\tFound {:s} on reMarkable".format(rm_path))
            elif not on_rm:
                print("\tCould not find {:s} on reMarkable, skipping...".format(rm_path))
                continue

            # Check last modification date on reMarkable
            if verbose:
                print("\tChecking modification date.")
            attachment_metadata = rmapi.stat(rm_path)
            last_modified_str = attachment_metadata['ModifiedClient']
            # The UTC+0 timezone is sometimes denoted as Z, but this is
            # not recognized by datetime:
            # https://discuss.python.org/t/parse-z-timezone-suffix-in-datetime/2220/14
            last_modified_str = last_modified_str.replace('Z', '')
            # Zero-pad microseconds
            frac_seconds = re.match('\d+-\d+-\d+T\d+:\d+:\d+.(\d+)',
                                    attachment_metadata['ModifiedClient']).group(1)
            if len(frac_seconds) < 6:
                last_modified_str += ('0' * (6 - len(frac_seconds)))
            last_modified_str += '+00:00'
            rm_last_modified = datetime.datetime.fromisoformat(last_modified_str)

            # Check to see if annotated file exists in zotero
            zot_remarks_attachment = attachment.replace('.pdf', ' _remarks.pdf')
            zot_attachment = zot_remarks_attachment if os.path.exists(zot_remarks_attachment) \
                else attachment
            # Check last modified date
            zot_last_modified = datetime.datetime.utcfromtimestamp(
                os.path.getmtime(zot_attachment))
                # Set UTC timezone for comparison
            zot_last_modified = zot_last_modified.replace(tzinfo=datetime.timezone.utc)

            # If file on computer is newer than on remarkable, skip this file.
            if zot_last_modified > rm_last_modified:
                if verbose:
                    print("\t\tFile on reMarkable not modified since last sync, skipping.")
                continue

            # Use remarks to extract PDF and MD
            if verbose:
                print("\tExtracting remarks")
            annotated_files = extract_remarks(rm_path, rmapi, config,
                                              metadata=attachment_metadata,
                                              verbose=verbose, targets=['md', 'pdf'])

            if len(annotated_files) > 0 and not dry_run:
                # Add extracted files to zotero notes
                if verbose:
                    print("\tAdding extracted highlights to zotero...")
                md_res = add_md_to_paper(paper, annotated_files[0], zot,
                                         verbose=verbose)
                # Remove md file
                os.remove(annotated_files[0])
                pdf_res = add_pdf_to_paper(zot_attach, annotated_files[1], zot, config,
                                           verbose=verbose)
    return


def send_papers(zot, rmapi, config, verbose=False, landscape=False,
                dry_run=False):
    '''
    Send papers to remarkable.
    '''
    z = zot.top(tag=config['zot_send_tag'])

    if verbose:
        print("Found {:d} papers to send.".format(len(z)))

    # Get list of files in Zotero storage dir
    pdflist = glob.glob(os.path.join(config['zot_storage_dir'], '*/*.pdf'))
    if pdflist == '':
        print("No PDF files found.")

    sent_papers = []
    for paper in z:
        if verbose:
            print("Preparing paper {:s}".format(paper['data']['title']))

        # Find PDF
        attachments = get_pdf_attachments(paper, zot, config)

        # If no attachments were found, skip the upload
        if not attachments:
            if verbose:
                print("\tNo attachments found, skipping upload")
            continue

        if verbose:
            for f in attachments:
                print("\tFound PDF attachment {:s}".format(os.path.basename(f)))

        # Get collection(s)
        collections = paper['data']['collections']
        hierarchy = get_collection_hierarchy(paper, zot, config)

        if verbose:
            print("\tPlacing attachments in folder {:s}".format('/'.join(hierarchy)))

        # Create target directory if it doesn't exist
        dirstr = rmapi.mkdir(hierarchy)

        # Upload attachments
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
                    print("\tDone converting to landscape.")

            # Check if file already exists
            rm_filename = dirstr + "/" + os.path.splitext(pdfname)[0]
            fileexists = rmapi.checkfile(rm_filename)
            if fileexists:
                if verbose:
                    print("\tFile {:s} already exists, skipping.".format(pdfname))
            else:
                # Upload file
                if not dry_run:
                    status = rmapi.put(attachment, dirstr)
                    if verbose:
                        print("\tUploaded {:s}.".format(pdfname))
                    sent_papers.append(paper)

            # Update tags in zotero
            if not dry_run:
                paper['data']['tags'] = [tag for tag in paper['data']['tags']
                                         if tag['tag'] != config['zot_send_tag']]
                if config['zot_replace']:
                    paper['data']['tags'].append({'tag': config['zot_replace_tag']})

                zot.update_item(paper)

            if verbose:
                print("\tUpdated tags.")

    return sent_papers


def main(verbose=False, landscape=False, dry_run=False, send=True, sync=True):
    # Read configuration file
    config = read_config()
    rmapi = RMAPI(config['rmapi_path'], verbose=verbose)
    zot = zotero.Zotero(config['zot_lib_id'], 'user', config['zot_api_key'])

    # Send papers
    # -----------
    if send:
        if verbose:
            print("Sending papers...")
        sent_papers = send_papers(zot, rmapi, config, verbose=verbose, landscape=landscape,
                                  dry_run=dry_run)

    # Backsync papers
    # ---------------
    if sync:
        if verbose:
            print("Syncing annotations...")
        backsync_papers(zot, rmapi, config, verbose=verbose, dry_run=dry_run, exclude=sent_papers)


    return

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Send papers from Zotero to ReMarkable tablet.")
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--landscape', '-l', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--send', action='store_true', help='Only send papers')
    parser.add_argument('--sync', action='store_true', help='Only sync papers')
    args = parser.parse_args()

    send = not args.sync
    sync = not args.send

    main(args.verbose, args.landscape, args.dry_run, send, sync)


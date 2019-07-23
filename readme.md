zotrm.py
========

A Python script to sync Zotero papers to the ReMarkable tablet.

Inspired by <https://github.com/GjjvdBurg/arxiv2remarkable/> and
<https://github.com/michaelmior/zotero-remarkable>. The main difference with the
latter is the use of collections as subdirectories and using the locally-stored
PDFs instead of requiring the files be synced via Zotero Sync or a WebDAV
server.

Usage
-----
Simply download the repository and run `python zotrm.py`.

Requirements
------------
- [rmapi](https://github.com/juruen/rmapi). This can be downloaded as a compiled
  executable from the link, or compiled from source using `go` (recommended).
- [pyzotero](https://github.com/urschrei/pyzotero). This can be installed using
  `pip` or `conda`.

Configuration
-------------
Place a `config.ini` file into `$USER/.zotrm/`.
- Zotero settings
	- `LIBRARY_ID`: Can be found [here](https://www.zotero.org/settings/keys),
	  as the user ID for API calls.
	- `API_KEY`: Can be obtained
	  [here](https://www.zotero.org/settings/keys/new).
	- `STORAGE_DIR`: Directory that Zotero uses for storing PDFs.
	- `SEND_TAG`: Tag to monitor for PDFs to send. Removed from item if
	  successfully sent or if file already existed.
	- `REPLACE_TAG`: Optional, a tag to add to sent PDFs.
- RMAPI settings
	- `RMAPI_PATH`: Path to rmapi executable.
- Remarkable settings
	- `BASE_DIR`: If a file is in a collection (or subcollection), it will be
	  placed in a folder(s) of the same name in this directory.
	- `DEFAULT_DIR`: If a file has no collection, it will be placed in this
	  directory.

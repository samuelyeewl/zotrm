zotrm.py
========

A Python script to sync Zotero papers to the ReMarkable tablet.

Inspired by <https://github.com/GjjvdBurg/arxiv2remarkable/> and
<https://github.com/michaelmior/zotero-remarkable>. The main difference with the
latter is the use of collections as subdirectories and using the locally-stored
PDFs instead of requiring the files be synced via Zotero Sync or a WebDAV
server.

remarks branch
--------------
This branch is home to an experimental feature, using a fork of the package
[remarks](https://github.com/lucasrla/remarks) to sync the annotated PDF and
extract the highlights back as notes in Zotero.

Features:
- Checks papers in zotero marked with `REPLACE_TAG` for new annotations.
- Generates a highlighted PDF and adds it as a new attachment in zotero.
- Extracts highlights and adds them as a note attachment in zotero.

Warning: there is no way to check whether a paper has been modified on the
remarkable without syncing it, which is a slow process. I suggest removing the
`REPLACE_TAG` for most papers in Zotero except the ones you want to keep synced.

Please open a pull request if you find any bugs.


Usage
-----
Simply download the repository and run `python zotrm.py`.

Requirements
------------
- [rmapi](https://github.com/juruen/rmapi). This can be downloaded as a compiled
  executable from the link, or compiled from source using `go` (recommended).
- [pyzotero](https://github.com/urschrei/pyzotero). This can be installed using
  `pip` or `conda`.
- The `zotrm` branch in my fork of [remarks](https://github.com/samuelyeewl/remarks)
  annotations back to Zotero.

Configuration
-------------
Place a `config.ini` file into `$USER/.zotrm/`.
- Zotero settings
    - `LIBRARY_ID`: Can be found [here](https://www.zotero.org/settings/keys),
      as the user ID for API calls.
    - `API_KEY`: Can be obtained
      [here](https://www.zotero.org/settings/keys/new).
    - `STORAGE_DIR`: Directory that Zotero uses for storing PDFs.
    - `ATTACHMENT_DIR`: Directory used for linked attachment files.
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
- remarks settings
    - `REMARKS_PATH`: Path to the `zotrm` branch of `remarks`.

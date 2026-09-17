# Built-in JavaScript worksheet functions

The generated add-in includes four functions, even without notebook exports:

| Formula | Result |
| --- | --- |
| `=JUPYTER.MANIFESTURL()` | Configured hosted manifest URL, including the Hub user subfolder |
| `=JUPYTER.SERVERURL()` | Configured Jupyter API base URL |
| `=JUPYTER.ADDINVERSION()` | Python package version used to generate the add-in |
| `=JUPYTER.ASSETVERSION()` | Loaded generated asset batch version |

They run locally in JavaScript without a token, network call, or Python kernel.
MANIFESTURL does not identify the uploaded/cached manifest Excel originally
installed. Values describe the configuration loaded by this add-in; old cached
assets can report an older asset version. No token is exposed.

Implementations and metadata live in `jupyterexcel/addin_template/builtin-functions.js`
and `builtin-functions.json`. Generation bundles their registrations into
functions.js and merges their metadata into functions.json. Their IDs are
reserved and cannot also be exported by notebooks. Notebook functions remain
in the metadata before built-ins. Unchanged saves retain the existing asset version.

After upgrading, generate assets by saving a notebook. Excel must reload its
custom-function metadata to discover the new formulas; updating the files alone
does not guarantee an already open workbook refreshes its formula list.

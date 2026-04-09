# PY_WITHDRAWAL_RETURN

Python ETL batch pipeline that processes SEPA direct debit mandate **acknowledgement return files** sent back by the clearing house partner, and injects the accepted/rejected status into the corresponding outbound fixed-width files.

## Overview

After the outbound mandate files are transmitted, the clearing house returns CSV acknowledgement files — one per mandate operation type. This program:

1. Detects and matches each return CSV with its original outbound fixed-width file (by timestamp in the FSTS header).
2. Parses the partner response map (mandate external ID → status + reason code + RUM).
3. Injects `ACCT` (accepted) or `RJCT` (rejected) at byte-precise positions in the outbound file.
4. Produces a consolidated processing log and summary.

## Supported message types

| Module      | Operation              | Input pattern                          |
|-------------|------------------------|----------------------------------------|
| `creat.py`  | MAMT001 – Creation     | `PROD.MAMT001_creat-mandats_*_R.csv`   |
| `modif.py`  | MAMT002 – Modification | `PROD.MAMT002_modif-mandats_*_R.csv`   |
| `annul.py`  | MAMT003 – Cancellation | `PROD.MAMT003_annul-mandats_*_R.csv`   |
| `activ.py`  | MAMT004 – Reactivation | `PROD.MAMT004_activ-mandats_*_R.csv`   |

## Project structure

```
PY_WITHDRAWAL_RETURN/
├── launcher/
│   └── PY_WITHDRAWAL_RETURN.cmd   # Windows batch launcher
├── programs/
│   ├── main.py                    # Entry point, orchestrates all modules
│   ├── creat.py                   # MAMT001 return processor
│   ├── modif.py                   # MAMT002 return processor
│   ├── annul.py                   # MAMT003 return processor
│   ├── activ.py                   # MAMT004 return processor
│   └── utils.py                   # Shared utilities (logger, path helpers)
├── input/                         # Drop zone for source outbound + return files
├── output/                        # Processed outbound files (status injected)
├── logs/                          # Application logs
└── requirements.txt
```

## Configuration

The program reads `config.ini` (located one level above `programs/`):

```ini
[paths]
input_dir  = C:\path\to\input
output_dir = C:\path\to\output
log_dir    = C:\path\to\logs

[env]
ENV = PROD   # or NONPROD

[patterns]
mamt001_return = PROD.MAMT001_creat-mandats_*_R.csv
mamt002_return = PROD.MAMT002_modif-mandats_*_R.csv
mamt003_return = PROD.MAMT003_annul-mandats_*_R.csv
mamt004_return = PROD.MAMT004_activ-mandats_*_R.csv
```

## Requirements

- Python 3.10+
- `pandas`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Windows — via the provided launcher (sets up venv automatically)
launcher\PY_WITHDRAWAL_RETURN.cmd

# Or directly
python programs/main.py PY_WITHDRAWAL_RETURN
```

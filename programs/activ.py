import os
import sys
import csv
import logging
import re
from datetime import datetime
import glob

from utils import load_config  # comme creat/modif

# ----------------- LOGS / CONFIG -----------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
paths, patterns = load_config(BASE_DIR)

ENV = paths["env"]
retour_dir = paths["retour_dir"]
output_dir = paths["output_dir"]
log_dir = paths["log_dir"]

os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "activ.log")

logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ----------------- CONSTS I/O -----------------
OUT_ENCODING = "cp1252"
NEWLINE = "\r\n"

# ----------------- REGEX -----------------
_batch_long_re = re.compile(r"(BATCH\d{15})")
_digits_re = re.compile(r"(\d+)")
# Date 14 chiffres juste avant BATCH dans le FSTS: ...YYYYMMDDHHMMSSBATCH...
_fsts_date_re = re.compile(r"(\d{14})BATCH")

# ----------------- HELPERS -----------------
def setup_logging():
    logging.info("Démarrage du script activ.py (PY_SEPA_RETOUR / MAMT004).")

def remove_slashes(line: str) -> str:
    return line.replace("/", " ")

def extract_batch_long_from_fsts(fsts_line: str) -> str:
    m = _batch_long_re.search(fsts_line or "")
    return m.group(1) if m else ""

def extract_date14_from_fsts(fsts_line: str) -> str:
    """
    Extrait YYYYMMDDHHMMSS depuis le FSTS (juste avant BATCH).
    Exemple: ...20260209205158BATCH...
    """
    m = _fsts_date_re.search(fsts_line or "")
    return m.group(1) if m else ""

def ensure_len(s: str, length: int) -> str:
    s = s or ""
    return s[:length].ljust(length)

def open_text_auto(path: str):
    try:
        return open(path, "r", encoding="utf-8-sig", newline="")
    except UnicodeDecodeError:
        return open(path, "r", encoding="cp1252", newline="")

def read_aller_lines(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return f.read().splitlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="cp1252", newline="") as f:
            return f.read().splitlines()

def parse_partnerTsi_header_first_line(retour_file: str) -> tuple[str, str]:
    """
    1ère ligne technique :
    TESSI-MDT;3;0;2026-02-04T20:22:11.000+02:00;...
    -> DATE_FMT = 20260204202211
    -> BATCH = parts[2] (souvent "0")
    """
    with open_text_auto(retour_file) as f:
        first = f.readline().strip()

    parts = first.split(";")
    if len(parts) < 4:
        raise ValueError("Première ligne CSV retour invalide (moins de 4 champs).")

    batch = parts[2].strip()
    date_raw = parts[3].strip()
    date_raw19 = date_raw[:19]  # "YYYY-MM-DDTHH:MM:SS"
    date_obj = datetime.strptime(date_raw19, "%Y-%m-%dT%H:%M:%S")
    date_fmt = date_obj.strftime("%Y%m%d%H%M%S")

    return date_fmt, batch

def build_partnerTsi_map(retour_file: str) -> dict[str, tuple[str, str, str]]:
    """
    EXTID -> (statut_AC112, code4, rum35)
    """
    partnerTsi_map: dict[str, tuple[str, str, str]] = {}

    with open_text_auto(retour_file) as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    if not rows:
        raise ValueError("Fichier retour CSV vide.")

    for idx, row in enumerate(rows[1:], start=2):
        if len(row) < 4:
            logging.warning(f"Ligne retour CSV {idx} ignorée (colonnes insuffisantes).")
            continue

        ack = row[0].strip()
        key_type = row[1].strip()
        extid = row[2].strip()
        rum = row[3].strip()

        if key_type != "EXTID":
            continue

        statut = "ACCT" if ack == "AR_V_00" else "RJCT"
        reject_code_raw = row[5].strip() if len(row) > 5 else ""
        code4 = reject_code_raw[:4].ljust(4) if statut == "RJCT" else (" " * 4)
        rum35 = rum[:35].ljust(35)

        partnerTsi_map[extid] = (statut, code4, rum35)

    return partnerTsi_map

def normalize_extid(value: str, detail_prefix: str) -> str:
    """
    Pour MAMT004 (ACTIV), on a vu des RUI qui commencent par:
      "050000006...."
    Donc on enlève les 9 premiers caractères si ça matche "050000006".
    """
    v = (value or "").strip()

    prefix9 = detail_prefix + "0000006"  # "050000006"
    if v.startswith(prefix9):
        v = v[9:].strip()

    groups = _digits_re.findall(v)
    return max(groups, key=len) if groups else v

def list_retour_files_mamt004() -> list[str]:
    """
    Liste tous les retours MAMT004 selon ENV/patterns.
    """
    if ENV.lower() == "prod":
        pat = patterns.get("mamt004_retour_prod", "UNEOPROD.MAMT004_activ-mandats_*_R.csv")
    else:
        # IMPORTANT: ton pattern actuel avait des minuscules + wildcard très large.
        # On met un pattern robuste, aligné avec les autres:
        pat = patterns.get("mamt004_retour_nonprod", "grpuneo.uneo-MAMT004_activ-mandats-*_R.csv")

    return sorted(glob.glob(os.path.join(retour_dir, pat)), key=os.path.getmtime, reverse=True)

def build_retour_index_by_date(retour_files: list[str]) -> dict[str, str]:
    """
    Indexe les retours par DATE_FMT (YYYYMMDDHHMMSS) lue dans la 1ère ligne technique.
    """
    idx: dict[str, str] = {}
    for rf in retour_files:
        try:
            date_fmt, _ = parse_partnerTsi_header_first_line(rf)
            idx[date_fmt] = rf
        except Exception as e:
            logging.warning(f"Index retour ignoré (parse KO) {os.path.basename(rf)}: {e}")
    return idx

# ----------------- CORE -----------------
def process_one_aller(aller_file: str, retour_by_date: dict[str, str]) -> None:
    if not os.path.exists(aller_file):
        raise FileNotFoundError(f"Fichier aller introuvable: {aller_file}")

    aller_lines = read_aller_lines(aller_file)
    if not aller_lines:
        raise ValueError("Fichier aller vide.")

    FSTS = aller_lines[0]
    OBS = str(max(0, len(aller_lines) - 1)).zfill(7)

    # Match EXACT via date FSTS
    date14 = extract_date14_from_fsts(FSTS)
    if not date14:
        raise ValueError("Impossible d'extraire YYYYMMDDHHMMSS depuis FSTS (pattern ...YYYYMMDDHHMMSSBATCH...).")

    retour_file = retour_by_date.get(date14, "")
    if not retour_file:
        raise ValueError(f"Aucun fichier retour MAMT004 correspondant à DATE={date14} dans {retour_dir}")

    DATE, BATCH = parse_partnerTsi_header_first_line(retour_file)
    partnerTsi_map = build_partnerTsi_map(retour_file)

    batch_long = extract_batch_long_from_fsts(FSTS)
    if not batch_long:
        raise ValueError("Impossible de trouver BATCHxxxxxxxxxxxxxxx dans l'entête FSTS du fichier aller.")
    batch_long = batch_long[:20].ljust(20)

    logging.info(
        f"[MATCH] aller={os.path.basename(aller_file)} DATE_FSTS={date14} "
        f"-> retour={os.path.basename(retour_file)} (DATE_RET={DATE}, BATCH_RET={BATCH})"
    )
    logging.info(f"Réponses TESSI chargées={len(partnerTsi_map)} / OBS={OBS}")

    part_field = "".ljust(15)
    flow_code = "MAMT004 "

    premiere_ligne = (
        ensure_len(FSTS[:37], 37) +
        ensure_len("UNEO", 35) +
        ensure_len("INFINITE", 35) +
        ensure_len(DATE, 14) +
        batch_long +
        part_field +
        flow_code +
        batch_long +
        (" " * 15) +
        ensure_len(OBS, 7) +
        "\n"
    )

    os.makedirs(output_dir, exist_ok=True)
    output_filename = os.path.basename(aller_file).replace("TXT", "OUT.TXT")
    output_file = os.path.join(output_dir, output_filename)

    # MAMT004 : statut en position 3008 => détail = 3007 chars avant append
    DETAIL_LEN = 3007
    DETAIL_PREFIX = "05"
    STATUS_BYTE_INDEX = 3007  # index 0-based bytes où commence ACCT/RJCT

    nb_ok = 0
    nb_missing = 0
    nb_written = 0

    with open(output_file, "wb") as out:
        out.write(premiere_ligne.replace("\n", NEWLINE).encode(OUT_ENCODING, errors="strict"))
        nb_written += 1

        for line_no, line in enumerate(aller_lines[1:], start=2):
            raw = line

            if not raw.startswith(DETAIL_PREFIX):
                out.write((raw + NEWLINE).encode(OUT_ENCODING, errors="strict"))
                nb_written += 1
                continue

            raw = raw.ljust(DETAIL_LEN)[:DETAIL_LEN]

            # RUI pos10 len35 => [9:44]
            extid = normalize_extid(raw[9:44], DETAIL_PREFIX)

            if extid not in partnerTsi_map:
                nb_missing += 1
                logging.warning(f"EXTID absent du retour TESSI: {extid} (ligne aller {line_no})")
                out.write((raw + NEWLINE).encode(OUT_ENCODING, errors="strict"))
                nb_written += 1
                continue

            statut, code4, rum35 = partnerTsi_map[extid]

            # RUM pos45 len35 => [44:79]
            raw_with_rum = raw[:44] + rum35 + raw[79:]

            # Statut pos3008 + code pos3012 (append)
            final_line = remove_slashes(raw_with_rum + statut + code4)

            b = (final_line + NEWLINE).encode(OUT_ENCODING, errors="strict")
            motif = b[STATUS_BYTE_INDEX:STATUS_BYTE_INDEX + 4]
            if motif not in (b"ACCT", b"RJCT"):
                logging.error(f"Motif KO en octets ligne {line_no}: motif={motif} len_bytes={len(b)} extid={extid}")

            out.write(b)
            nb_written += 1
            nb_ok += 1

    logging.info(f"Terminé: {os.path.basename(aller_file)} lignes={nb_written} OK={nb_ok} missing={nb_missing} output={output_file}")

def main():
    setup_logging()

    if len(sys.argv) < 2:
        logging.error("Argument manquant: au moins un fichier INFINITE.MAMT004*")
        raise SystemExit(2)

    aller_files = sys.argv[1:]
    retour_files = list_retour_files_mamt004()
    retour_by_date = build_retour_index_by_date(retour_files)

    ok = 0
    ko = 0

    for af in aller_files:
        try:
            process_one_aller(af, retour_by_date)
            ok += 1
        except Exception as e:
            ko += 1
            logging.exception(f"[KO] {os.path.basename(af)}: {e}")

    raise SystemExit(2 if ko > 0 else 0)

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        logging.exception(f"Erreur lors de l'exécution du script : {e}")
        raise SystemExit(2)

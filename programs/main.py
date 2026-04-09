import glob
import os
import subprocess
import sys

from utils import setup_logger, load_config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
paths, patterns = load_config(BASE_DIR)

log = setup_logger("PY_SEPA_RETOUR_MAIN", paths["log_dir"])

# Sources = PY_SEPA_ALLER/input/tmp (ou ton chemin équivalent)
chemin_sources = paths["chemin_sources"]
output_dir = paths["output_dir"]
programs_dir = paths["programs_dir"]

os.makedirs(output_dir, exist_ok=True)

aller_glob = patterns.get("aller_glob", "INFINITE.MAMT*.TXT*")
pattern_full = os.path.join(chemin_sources, aller_glob)

log.info(f"[DEBUG] Dossier source : {chemin_sources}")
log.info(f"[DEBUG] Pattern       : {pattern_full}")

fichiers_sources = sorted(glob.glob(pattern_full))
log.info(f"[DEBUG] Fichiers trouvés : {len(fichiers_sources)}")

if not fichiers_sources:
    log.info("Aucun fichier INFINITE trouvé -> fin du programme.")
    sys.exit(0)

fichiers_traites = []
fichiers_crees = []
fichiers_supprimes = []
fichiers_en_erreur = []


def list_outputs():
    """Snapshot des fichiers présents dans output_dir (pour diff avant/après)."""
    return set(glob.glob(os.path.join(output_dir, "*")))


for fichier in fichiers_sources:
    nom_fichier = os.path.basename(fichier)
    fichiers_traites.append(nom_fichier)

    # Prefixe = MAMT001, MAMT002, ...
    try:
        prefixe = nom_fichier.split(".")[1]
    except Exception:
        log.info(f"[SKIP] Nom inattendu : {nom_fichier}")
        continue

    if prefixe == "MAMT001":
        script = os.path.join(programs_dir, "creat.py")
    elif prefixe == "MAMT002":
        script = os.path.join(programs_dir, "modif.py")
    elif prefixe == "MAMT003":
        script = os.path.join(programs_dir, "annul.py")
    elif prefixe == "MAMT004":
        script = os.path.join(programs_dir, "activ.py")
    else:
        log.info(f"[SKIP] Prefixe non géré : {prefixe} ({nom_fichier})")
        continue

    # Snapshot outputs avant
    before = list_outputs()

    try:
        # Traitement DIRECT sur le fichier dans PY_SEPA_ALLER/input/tmp (sans copie tmp RETOUR)
        subprocess.run([sys.executable, script, fichier], check=True)

        # Snapshot outputs après + détection des nouveaux fichiers
        after = list_outputs()
        new_files = sorted(after - before, key=os.path.getmtime, reverse=True)

        if new_files:
            for nf in new_files:
                fichiers_crees.append(os.path.basename(nf))
        else:
            # fallback : log, sans bloquer (au cas où le script écrase un fichier existant)
            log.info(f"[WARN] Aucun nouveau fichier détecté dans output_dir après {nom_fichier}")

        # Suppression du fichier source SEULEMENT si OK
        os.remove(fichier)
        fichiers_supprimes.append(nom_fichier)
        log.info(f"[CLEAN] Supprimé du dossier source : {fichier}")

    except subprocess.CalledProcessError as e:
        fichiers_en_erreur.append(nom_fichier)
        log.error(f"[ERREUR] Traitement KO pour {nom_fichier} (code={e.returncode}) -> fichier conservé")
        continue

    except Exception:
        fichiers_en_erreur.append(nom_fichier)
        log.exception(f"[ERREUR] Exception inattendue sur {nom_fichier} -> fichier conservé")
        continue


log.info("===== RÉCAPITULATIF TRAITEMENT SEPA_RETOUR =====")
log.info("Fichiers traités :")
for f in fichiers_traites:
    log.info(f" - {f}")

log.info("Fichiers créés :")
for f in fichiers_crees or ["Aucun fichier créé"]:
    log.info(f" - {f}")

log.info("Fichiers supprimés du dossier source (PY_SEPA_ALLER/input/tmp) :")
for f in fichiers_supprimes or ["Aucun fichier supprimé"]:
    log.info(f" - {f}")

if fichiers_en_erreur:
    log.info("Fichiers en erreur (conservés) :")
    for f in fichiers_en_erreur:
        log.info(f" - {f}")

log.info("================================================")

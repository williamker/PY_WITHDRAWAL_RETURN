import logging
from datetime import datetime
import os
import configparser
from base64 import b64decode

import pandas as pd
from typing import Optional



# Save output csv files
def export_df_csv(df, file_directory, file_name, extension: str = "csv", is_extension: str = True, is_date: str = True, **kwargs):
    """
    Saves a DataFrame to a CSV file with a date-based filename.

    Parameters:
    df (pd.DataFrame): The DataFrame to save.
    file_name (str): The base name of the CSV file.
    
    Returns:
    str: The full path of the saved CSV file.
    """
    
    # Get the current date and time
    current_time = datetime.now().strftime('%Y.%m.%d_%H.%M.%S')
    
    # Create the full file name
    if is_date==True:
        if is_extension==True:
            full_file_name = f"{file_name}_{current_time}.{extension}"
        else:
            full_file_name = f"{file_name}_{current_time}"
    else:
        if is_extension==True:
            full_file_name = f"{file_name}.{extension}"
        else:
            full_file_name = f"{file_name}"
    
    # Create the full path
    full_path = os.path.join(file_directory, full_file_name)
    
    # Save the DataFrame to CSV
    df.to_csv(full_path, index=False, **kwargs)
    
    return full_path

def setup_logger(prog_name, logs_path):
    """
    Configure et retourne un logger pour le programme.
    """
    if prog_name in logging.root.manager.loggerDict:
        return logging.getLogger(prog_name)  # Retourne le logger existant

    current_date = datetime.now().strftime('%Y%m%d')
    
    
    # Creer le dossier logs s'il n'existe pas
    os.makedirs(logs_path, exist_ok=True)

    log_file_path = os.path.join(logs_path, f'{prog_name}_{current_date}.log')

    logger = logging.getLogger(prog_name)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(f"[{prog_name}] %(asctime)s [%(levelname)s] %(message)s", datefmt='%Y-%m-%d %H:%M:%S')

    file_handler = logging.FileHandler(log_file_path, delay=True)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.propagate = False

    return logger




def format_time(seconds):
    """Convertit un temps en secondes en un format lisible (heures:minutes:secondes)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:.2f}"

def list_dir( path: str, logger: logging.Logger) -> list[str]:
    """
    Traite un repertoire et ecrit des logs selon les regles definies.
    
    Parameters:
        path (str): 
        logger (logging.Logger): Logger 
        
    
    Returns
        None si le repertoire n'existe pas
        [] si le repertoire est vide
        [] si le repertoire contient uniquement un fichiers .git*
        list of files of the directory different without git files
    """
    # Verifier si le repertoire existe
    if not os.path.isdir(path):
        logger.error(f"Le repertoire {path} n'existe pas")
        return None

    # Lister les files du repertoire
    files = os.listdir(path)

    # Verifier si le repertoire est vide
    if not files :
        logger.info("Le repertoire {path} est vide")
        return []

    #si le repertoire contient uniquement un fichiers .git*
    if len(files) == 1 and "git" in files[0].lower():
        logger.info(f"Le repertoire {path} n'est pas vide, il contient uniquement le fichier {files[0]}")
        return []


    # Sinon, lister les files dans la log  et retourner la liste des files sans les fichiers git
    files1=[]
    for file in files:
        if "git" not in file:
            files1.append(file)
    
    logger.info(f"Listing du repertoire input {path}:")
    for file in files1:
        logger.info(f" -> {file}")
    return files1




def execute_odbc_query_to_df(
    environnement: str,
    server: str,
    database: str,
    user: str,
    password: str,
    driver: str,
    sql_file_path: str,
    log
) -> Optional[pd.DataFrame]:
    """
    Execute une requête SQL stockee dans un fichier et retourne le resultat sous forme de DataFrame Pandas.

    Parametres :
    -----------
    environnement : str
        Nom ou identifiant de l'environnement de la base de donnees (pour le logging).
    server : str
        Nom ou IP du serveur de base de donnees.
    database : str
        Nom de la base de donnees.
    user : str
        Nom d'utilisateur pour la connexion.
    password : str
        Mot de passe chiffre pour la connexion (sera dechiffre avant usage).
    driver : str
        Driver ODBC à utiliser pour la connexion.
    sql_file_path : str
        Chemin du fichier SQL contenant la requête à executer.
    log : Logger
        Objet logger pour enregistrer les messages d'information et d'erreur.

    Retour :
    --------
    pd.DataFrame | None
        Retourne un DataFrame contenant le resultat de la requête SQL. 
        Retourne None si une erreur survient.

    Exceptions :
    ------------
    Toutes les exceptions sont interceptees et loggees. Aucun exception n’est levee directement.
    """

    try:
        # Utiliser un context manager pour garantir la fermeture de la connexion
        with pyodbc.connect(
            server=server,
            user=user,
            database=database,
            driver=driver,
            password=password
        ) as conn:

            log.info(f"Connecte avec succes au SID: {environnement}")

            # Lire le contenu du fichier SQL
            with open(sql_file_path, "r", encoding="utf-8") as file:
                sql_query = file.read()

            # Executer la requête SQL et charger le resultat dans un DataFrame
            df = pd.read_sql_query(sql_query, conn)

            return df

    except Exception as e:
        # En cas d’erreur, logger l’exception et retourner None
        log.error(f"Erreur lors de l'execution de la requête : {e}")
        return None


import os
import configparser

def load_config(base_dir: str):
    """
    base_dir = racine du projet PY_SEPA_RETOUR (là où est config.ini)
    """
    cfg_path = os.path.join(base_dir, "config.ini")
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"config.ini introuvable : {cfg_path}")

    config = configparser.ConfigParser()
    config.read(cfg_path, encoding="utf-8")

    env = config.get("settings", "ENV", fallback="dev").strip()
    sect = f"path.{env}"
    if sect not in config:
        raise KeyError(f"Section manquante dans config.ini: [{sect}]")

    paths = {
        "env": env,
        "chemin_sources": config.get(sect, "chemin_sources"),
        "retour_dir": config.get(sect, "retour_dir"),
        "tmp_dir": config.get(sect, "tmp_dir"),
        "output_dir": config.get(sect, "output_dir"),
        "log_dir": config.get(sect, "log_dir"),
        "programs_dir": config.get(sect, "programs_dir"),
    }

    patterns = dict(config.items("patterns")) if config.has_section("patterns") else {}

    return paths, patterns

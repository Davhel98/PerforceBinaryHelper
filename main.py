import os
import json
import shutil
import subprocess
from P4 import P4, P4Exception
import stat

def make_writable(path):
    for root, dirs, files in os.walk(path):
        for name in files:
            filepath = os.path.join(root, name)
            try:
                os.chmod(filepath, stat.S_IWRITE)
            except Exception as e:
                print(f"Errore nel rendere scrivibile {filepath}: {e}")
        for name in dirs:
            dirpath = os.path.join(root, name)
            try:
                os.chmod(dirpath, stat.S_IWRITE)
            except Exception as e:
                print(f"Errore nel rendere scrivibile {dirpath}: {e}")
    try:
        os.chmod(path, stat.S_IWRITE)
    except Exception as e:
        print(f"Errore nel rendere scrivibile {path}: {e}")

def force_add_or_edit(p4, path, change_num):
    try:
        fstat = p4.run_fstat(path)
        if fstat and "depotFile" in fstat[0]:
            # Già sotto versionamento → forza edit
            p4.run_edit("-c", change_num, path)
            print(f"[EDIT] {path}")
        else:
            # Non tracciato → forza add
            p4.run_add("-c", change_num, path)
            print(f"[ADD] {path}")
    except P4Exception as e:
        print(f"[ERRORE] {path}: {e}")

# === 1. Carica configurazione da JSON ===
CONFIG_FILE = "./p4_config.json"
if not os.path.exists(CONFIG_FILE):
    print(f"File di configurazione '{CONFIG_FILE}' non trovato.")
    input("Assicurati che il file esista e premi Invio per uscire...")
    exit(1)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

P4SERVER = config["p4server"]
P4USER = config["p4user"]
P4PASS = config["p4password"]
P4WORKSPACE = config["p4workspace"]
PROJECT_DIR = config["project_dir"]
UE_BUILD_TOOL = config["ue_build_tool"]
CHANGE_DESC = config["change_desc"]
PROJECT_FILENAME = config["project_filename"]
REBUILD_BINARIES = config["bRebuildProject"]

UE_PROJECT_FILE = os.path.join(PROJECT_DIR, PROJECT_FILENAME)
BINARIES_DIR = os.path.join(PROJECT_DIR, "Binaries")

# === 2. Rimozione e ricompilazione ===
if REBUILD_BINARIES:
    if os.path.exists(BINARIES_DIR):
        print("Rendo la cartella Binaries scrivibile...")
        make_writable(BINARIES_DIR)
        print(f"Cancello {BINARIES_DIR}...")
        shutil.rmtree(BINARIES_DIR)
    else:
        print("Cartella Binaries già assente.")

    print("Compilazione progetto Unreal...")
    project_name = os.path.splitext(os.path.basename(UE_PROJECT_FILE))[0]
    target_name = f"{project_name}Editor"
    build_cmd = [
        UE_BUILD_TOOL,
        target_name,
        "Win64",
        "Development",
        "-project=" + UE_PROJECT_FILE,
        "-waitmutex",
        "-NoHotReloadFromIDE"
    ]
    try:
        subprocess.check_call(build_cmd)
        print("Compilazione completata.")
    except subprocess.CalledProcessError as e:
        print(f"Errore nella compilazione: {e}")
        input("Assicurati che il file esista e premi Invio per uscire...")
        exit(1)
else:
    print("Ricompilazione disabilitata. Si assume che Binaries sia già presente e aggiornata.")

# === 3. Connessione a Perforce ===
p4 = P4()
p4.port = P4SERVER
p4.user = P4USER
p4.client = P4WORKSPACE

try:
    p4.connect()
    p4.password = P4PASS
    p4.run_login()

    # === 4. Cerca o crea changelist ===
    changes = p4.run_changes("-s", "pending", "-u", P4USER, "-c", P4WORKSPACE)
    change_num = None
    for c in changes:
        desc = p4.run_describe(c["change"])[0]
        if CHANGE_DESC in desc["desc"]:
            change_num = c["change"]
            break

    if not change_num:
        print("Creo una nuova changelist vuota...")
        new_change = p4.fetch_change()
        new_change["Description"] = CHANGE_DESC
        new_change["Files"] = []
        saved = p4.save_change(new_change)
        change_num = saved[0].split()[1]

    # === 5. Forza add/edit dei file ===
    print(f"Forzo l'aggiunta/edit dei file in {BINARIES_DIR} nella changelist {change_num}...")
    for root, dirs, files in os.walk(BINARIES_DIR):
        for file in files:
            full_path = os.path.abspath(os.path.join(root, file))
            force_add_or_edit(p4, full_path, change_num)

    print("Tutti i file sono stati processati.")
    input("Premi Invio per continuare...")

finally:
    p4.disconnect()
    input("Premere un tasto per continuare...")

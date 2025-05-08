import os

if os.path.exists('database.sqlite3'):
    os.remove('database.sqlite3')
    print("Ancienne base de données supprimée.")
else:
    print("Aucune base de données existante trouvée.")

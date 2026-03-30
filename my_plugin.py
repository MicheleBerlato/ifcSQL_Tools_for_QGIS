# Importa librerie di QGIS
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox, QDialog, QAbstractItemView, QMainWindow, QFileDialog, QProgressDialog, QApplication, QDockWidget, QListWidgetItem, QDockWidget
from qgis.PyQt.QtGui import QIcon, QColor, QStandardItemModel, QStandardItem, QCursor
from qgis.PyQt.QtCore import QSettings, Qt, QSortFilterProxyModel, pyqtSignal, QCoreApplication, QTranslator, QThread
from qgis.core import Qgis, QgsMessageLog, QgsVectorLayer, QgsDataSourceUri, QgsProject, QgsPointXY, QgsGeometry, QgsWkbTypes, QgsFeature, QgsField
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand, QgsVertexMarker, QgsMapCanvas, QgsMapToolPan


# Importa librerie standard di Python
import os
import re
import subprocess
import time
from math import atan2, cos, sin
import threading
import sys          
import importlib
import zipfile
import site



# Definisce flag per nascondere le finestre di console su Windows
if os.name == 'nt':
    HIDE_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW
else:
    HIDE_WINDOW_FLAGS = 0

# Importa librerie esterne 
try:
    import ifcopenshell
    IFCOPENSHELL_PRESENTE = True
except ImportError:
    IFCOPENSHELL_PRESENTE = False # La libreria non è installata

try:
    import trimesh
    TRIMESH_PRESENTE = True
except ImportError:
    TRIMESH_PRESENTE = False

try:
    import numpy as np
    NUMPY_PRESENTE = True
except ImportError:
    NUMPY_PRESENTE = False

try:
    import psycopg2
    PSYCOPG2_PRESENTE = True
except ImportError:
    PSYCOPG2_PRESENTE = False

try:
    import pyodbc
    PYODBC_PRESENTE = True

    # Disabilita il connection pooling di pyodbc per evitare problemi di connessioni persistenti
    try:
        pyodbc.pooling = False
    except Exception:
        pass

except ImportError:
    PYODBC_PRESENTE = False
    
# Importa le interfacce grafiche generate da Qt Designer
from .UIs.ImportaIFC import Ui_InserisciFileIFC
from .UIs.EliminaIFC import Ui_EliminaProgettoIFC
from .UIs.DockQuery import Ui_Query
from .UIs.SelezionaProgettoDaEliminare import Ui_SelezionaProgetto




# --- CLASSI THREAD PER TEST CONNESSIONE DBs IN BACKGROUND ---
class PostgresConnectionThread(QThread):
    success = pyqtSignal(tuple)
    error = pyqtSignal(str)

    def __init__(self, host, database, username, password, port):
        super().__init__()
        self.params = (host, database, username, password, port)

    def run(self):
        host, database, username, password, port = self.params
        try:
            # Timeout di 15 sec: lungo abbastanza per non scartare connessioni lente
            conn = psycopg2.connect(
                host=host, database=database, user=username, password=password, port=port, connect_timeout=15
            )
            conn.close()
            self.success.emit(self.params)
        except Exception as e:
            self.error.emit(str(e))

class MssqlConnectionThread(QThread):
    success = pyqtSignal(tuple)
    error = pyqtSignal(str)

    def __init__(self, host, database, username, password):
        super().__init__()
        self.params = (host, database, username, password)

    def run(self):
        host, database, username, password = self.params
        try:
            conn_str_parts = [
                "DRIVER={ODBC Driver 17 for SQL Server}",
                f"SERVER={host}",
                f"DATABASE={database}",
                "TrustServerCertificate=yes"
            ]

            if username and str(username).strip() != "":
                conn_str_parts.append(f"UID={username}")
                conn_str_parts.append(f"PWD={password}")
            else:
                conn_str_parts.append("Trusted_Connection=yes")

            connection_string = ";".join(conn_str_parts)
            # Timeout 15 secondi
            conn = pyodbc.connect(connection_string, timeout=15)
            conn.close()
            self.success.emit(self.params)
        except Exception as e:
            self.error.emit(str(e))















#    ███    ███  █████  ██ ███    ██      ██████ ██       █████  ███████ ███████ 
#    ████  ████ ██   ██ ██ ████   ██     ██      ██      ██   ██ ██      ██      
#    ██ ████ ██ ███████ ██ ██ ██  ██     ██      ██      ███████ ███████ ███████ 
#    ██  ██  ██ ██   ██ ██ ██  ██ ██     ██      ██      ██   ██      ██      ██ 
#    ██      ██ ██   ██ ██ ██   ████      ██████ ███████ ██   ██ ███████ ███████ 
#                                                                                                       









#####################################################################
#classe principale del plugin
#####################################################################

class MyPlugin:
    def __init__(self, iface):
        super().__init__()
        self.iface = iface

        # --- BLOCCO TRADUZIONE ---
        # 1. Ottieni la lingua impostata su QGIS (es. 'it', 'en', 'fr')
        raw_locale = QSettings().value('locale/userLocale', 'en')[0:2]
        plugin_dir = os.path.dirname(__file__)
        
        # 2. Logica invertita: se NON è italiano, forza l'inglese
        if raw_locale != 'it':
            # Carichiamo il file di traduzione in INGLESE
            locale_path = os.path.join(plugin_dir, 'i18n', 'ifcsql_en.qm')
            
            self.translator = QTranslator()
            if os.path.exists(locale_path):
                self.translator.load(locale_path)
                QCoreApplication.installTranslator(self.translator)
        # 3. Se è 'it', non carichiamo nessun traduttore: Qt userà le stringhe originali del codice.
        # -------------------------

        # Inizializza le variabili del menu e della toolbar
        self.menu = None
        self.toolbar = None

        # Inizializza le variabili delle finestre di dialogo
        self.import_dialog = None  
        self.delete_dialog = None
        self.insert_dialog = None
        self.query_dialog = None   

        # Inizializza le azioni del menu e della toolbar
        self.action1 = None
        self.action2 = None
        self.action3 = None
        self.action4 = None

    # Funzione di utilità per la traduzione delle stringhe
    def tr(self, message):
        """Restituisce la stringa tradotta."""
        return QCoreApplication.translate('MyPlugin', message)

    # Inizializza l'interfaccia grafica del plugin

    def initGui(self):
        # Imposta il percorso del plugin
        plugin_directory = os.path.dirname(__file__)

        # Crea un sotto-menu chiamato "ifcSQL Tools" nel menu Database
        self.menu = QMenu("ifcSQL Tools", self.iface.mainWindow())
        icon = QIcon(os.path.join(plugin_directory, 'icons', 'icon.png'))
        self.menu.setIcon(icon)  # imposta l’icona correttamente in PyQt5
        self.iface.databaseMenu().addMenu(self.menu)

        # Pulsante 1
        self.action1 = QAction(QIcon(os.path.join(plugin_directory, 'icons', 'icon_insert2.png')), self.tr("Importa file IFC"), self.iface.mainWindow())
        self.menu.addAction(self.action1)
        self.action1.triggered.connect(self.run_import)

        # Pulsante 2
        self.action2 = QAction(QIcon(os.path.join(plugin_directory, 'icons', 'icon_delete.png')), self.tr("Elimina file IFC"), self.iface.mainWindow())
        self.menu.addAction(self.action2)
        self.action2.triggered.connect(self.run_delete)  # Aggiungi il metodo per gestire l'eliminazione

        # Pulsante 3
        #self.action3 = QAction(QIcon(os.path.join(plugin_directory, 'icons', 'icon_download2.png')),"Scarica file IFC", self.iface.mainWindow())
        #self.menu.addAction(self.action3)
        #self.action3.triggered.connect(self.run_insert)  # Aggiungi il metodo per gestire le query

        # --- BLOCCO DI PULIZIA AGGIUNTO --- Cerca se ci sono vecchi pannelli rimasti "appesi" dal reload precedente
        old_dock = self.iface.mainWindow().findChild(QDockWidget, "IfcSqlQueryDock")
        if old_dock:
            self.iface.removeDockWidget(old_dock) # Lo rimuove dalla GUI
            old_dock.deleteLater()                # Lo elimina dalla memoria

        # Pulsante 4
        self.action4 = QAction(QIcon(os.path.join(plugin_directory, 'icons', 'icon_query2.png')), self.tr("Query IFC"), self.iface.mainWindow())
        self.action4.setCheckable(True) 
        self.menu.addAction(self.action4)
        self.action4.triggered.connect(self.run_query)

        # -----------------------------------------------------------
        # 3. GESTIONE DELLA TOOLBAR DEDICATA
        #------------------------------------------------------------    
        # Crea una toolbar specifica per il tuo plugin
        self.toolbar = self.iface.addToolBar("ifcSQL Tools Toolbar")
        self.toolbar.setObjectName("ifcSQLToolsToolbar") # Importante per salvare la posizione nelle sessioni future

        # Aggiungi le azioni alla TUA toolbar 
        self.toolbar.addAction(self.action1)
        self.toolbar.addAction(self.action2)
        #self.toolbar.addAction(self.action3)
        self.toolbar.addAction(self.action4)

    # Rimuovi l'interfaccia grafica del plugin    

    def unload(self):
        # 1. Rimuovi il Dock Widget se esiste
        if self.query_dialog:
            self.iface.removeDockWidget(self.query_dialog)
            self.query_dialog.deleteLater()
            self.query_dialog = None
        
        # Rimuovi tutto dal menu e dalla toolbar
        if self.menu:
            self.iface.databaseMenu().removeAction(self.menu.menuAction())
        if self.toolbar:
            del self.toolbar

    # Funzioni per aprire le varie finestre di dialogo
    
    def run_import(self):
        if not self.import_dialog:
            self.import_dialog = ImportaIFCDialog(self.iface)
            self.import_dialog.import_completed.connect(self.force_query_reset)
        self.import_dialog.populate_connection_combo_MSSQL()  # qui popoliamo la combo box
        self.import_dialog.populate_connection_combo_PostgreSQL()  # qui popoliamo la combo box
        self.import_dialog.show()
    
    def run_delete(self):
        if not self.delete_dialog:
            self.delete_dialog = EliminaProgettoDialog(self.iface)
            self.delete_dialog.delete_completed.connect(self.force_query_reset)
        self.delete_dialog.populate_connection_combo_MSSQL_delete()  # qui popoliamo la combo box
        self.delete_dialog.populate_connection_combo_PostgreSQL_delete()  # qui popoliamo la combo box
        self.delete_dialog.show()

    def force_query_reset(self):
        """
        Chiamata automaticamente quando un progetto viene Importato o Eliminato.
        Resetta la finestra Query per costringere l'utente a riconnettersi e aggiornare le liste.
        """
        if self.query_dialog:
            # Usa il metodo che resetta tutto come se si cambiasse DB
            self.query_dialog.reset_ui_on_connection_change_PostgreSQL_Query()
    
    def run_query(self, checked):
        # --- 1. CREAZIONE E CONFIGURAZIONE INIZIALE (Solo la prima volta) ---
        if not self.query_dialog:
            self.query_dialog = QueryDialog(self.iface, parent=self.iface.mainWindow())
            self.query_dialog.setObjectName("IfcSqlQueryDock") 
            
            # [FIX DIMENSIONI] Impostiamo una dimensione minima gestibile
            # Questo impedisce che la finestra "esploda" verso il basso
            self.query_dialog.setMinimumWidth(300)
            self.query_dialog.setMinimumHeight(200)
            self.query_dialog.resize(350, 400) # Una dimensione di partenza ragionevole
            
            # Aggiungiamo il widget (inizialmente nascosto o visibile a seconda di checked)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.query_dialog)
            
            # Collega eventi
            self.query_dialog.visibilityChanged.connect(self.action4.setChecked)
            self.query_dialog.populate_connection_combo_PostgreSQL_Query()

        # --- 2. GESTIONE VISIBILITÀ E SCHEDE (Eseguito a ogni click) ---
        if checked:
            if not self.query_dialog.isVisible():
                self.query_dialog.show()
            
            # Chiamiamo la funzione helper per forzare le schede
            self.force_tabify_dock()
            
            self.query_dialog.raise_() # Porta in primo piano
        else:
            if self.query_dialog.isVisible():
                self.query_dialog.hide()

    # --- 3. NUOVA FUNZIONE HELPER PER GESTIRE L'AGGIANCIO ---
    def force_tabify_dock(self):
        """
        Cerca un altro pannello a destra e forza la creazione delle schede (Tabs).
        """
        mainWindow = self.iface.mainWindow()
        
        # Se il nostro pannello è già in una scheda insieme ad altri, non facciamo nulla!
        # Questo evita sfarfallii e riposizionamenti inutili.
        if mainWindow.tabifiedDockWidgets(self.query_dialog):
            return

        target_dock = None
        
        # A. Tentativo prioritario: Cerchiamo i pannelli standard di QGIS
        # "IdentifyResults" = Informazioni, "LayerOrder" = Ordine Layer
        priority_docks = ["IdentifyResults", "LayerOrder", "StatisticsDockWidget", "AdvancedDigitizingPanel"]
        
        for name in priority_docks:
            dock = mainWindow.findChild(QDockWidget, name)
            # Deve esistere, essere visibile, ed essere nella zona destra
            if (dock and dock.isVisible() and not dock.isFloating() and 
                mainWindow.dockWidgetArea(dock) == Qt.RightDockWidgetArea):
                target_dock = dock
                break
        
        # B. Tentativo generico: Se non troviamo i standard, prendiamo il primo a destra
        if not target_dock:
            all_docks = mainWindow.findChildren(QDockWidget)
            for dock in all_docks:
                if dock == self.query_dialog: continue
                if (dock.isVisible() and not dock.isFloating() and 
                    mainWindow.dockWidgetArea(dock) == Qt.RightDockWidgetArea):
                    target_dock = dock
                    break
        
        # C. Eseguiamo l'aggancio
        if target_dock:
            mainWindow.tabifyDockWidget(target_dock, self.query_dialog)











#    ██ ███    ███ ██████   ██████  ██████  ████████      ██████ ██       █████  ███████ ███████ 
#    ██ ████  ████ ██   ██ ██    ██ ██   ██    ██        ██      ██      ██   ██ ██      ██      
#    ██ ██ ████ ██ ██████  ██    ██ ██████     ██        ██      ██      ███████ ███████ ███████ 
#    ██ ██  ██  ██ ██      ██    ██ ██   ██    ██        ██      ██      ██   ██      ██      ██ 
#    ██ ██      ██ ██       ██████  ██   ██    ██         ██████ ███████ ██   ██ ███████ ███████ 
#                                                                                                
#                                                                                                                                                 








########################################################
# Classe per la finestra di dialogo di importazione IFC
#########################################################

class ImportaIFCDialog(Ui_InserisciFileIFC, QMainWindow):   

    import_completed = pyqtSignal()  # Segnale personalizzato per indicare che l'importazione è stata completata

    def __init__(self, iface):
        super().__init__()
        self.setupUi(self)
        self.iface = iface
        self.selected_ifc = None

        # Inizializza il LED grigio
        self.set_led_colorMSSQL("gray")
        self.set_led_colorPostgreSQL("gray")

        # Collega l'evento di cambio selezione della ComboBox
        self.comboBox_ConnessioneMSSQL.currentIndexChanged.connect(self.reset_ui_on_connection_change_MSSQL)
        self.comboBox_ConnessionePostgreSQL.currentIndexChanged.connect(self.reset_ui_on_connection_change_PostgreSQL)
        
        # Collega i pulsanti alle funzioni
        self.pushButton_CreaNuovaConnessioneMSSQL.clicked.connect(self.create_new_connection_MSSQL)
        self.pushButton_ConnettiMSSQL.clicked.connect(self.connect_selected_DB_MSSQL)
        self.pushButton_SelezionaIfcMSSQL.clicked.connect(self.scegli_file_ifc_MSSQL)
        self.pushButton_ImportaMSSQL.clicked.connect(self.import_ifc_file_MSSQL)
        
        self.pushButton_CreaNuovaConnessionePostgreSQL.clicked.connect(self.create_new_connection_PostgreSQL)
        self.pushButton_ConnettiPostgreSQL.clicked.connect(self.connect_selected_DB_PostgreSQL)
        self.pushButton_SelezionaIfcPostgreSQL.clicked.connect(self.scegli_file_ifc_PostgreSQL)
        self.pushButton_ImportaPostgreSQL.clicked.connect(self.handle_importa_postgres_click)


    #imposta il colore del LED per MSSQL e PostgreSQL

    def set_led_colorMSSQL(self, color_name):
        palette = self.label_led_MSSQL.palette()
        palette.setColor(self.label_led_MSSQL.backgroundRole(), QColor(color_name))
        self.label_led_MSSQL.setAutoFillBackground(True)
        self.label_led_MSSQL.setPalette(palette)
        self.label_led_MSSQL.show()

    def set_led_colorPostgreSQL(self, color_name):
        palette = self.label_led_PostgreSQL.palette()
        palette.setColor(self.label_led_PostgreSQL.backgroundRole(), QColor(color_name))
        self.label_led_PostgreSQL.setAutoFillBackground(True)
        self.label_led_PostgreSQL.setPalette(palette)
        self.label_led_PostgreSQL.show()

    # --- Funzioni di utilità per Logging ---
   
    def log_info(self, message):
        """Scrive nel pannello log di QGIS invece che nella messageBar"""
        QgsMessageLog.logMessage(message, "Importazione IFC", level=Qgis.Info)

    def log_error(self, message):
        """Scrive errore nel log e mostra popup"""
        QgsMessageLog.logMessage(message, "Importazione IFC", level=Qgis.Critical)
        QMessageBox.critical(self, "Errore", message)
    
    #resetta l'interfaccia utente quando si cambia la connessione selezionata MSSQL e PostgreSQL
    
    def reset_ui_on_connection_change_MSSQL(self):
        """Resetta il LED e l'etichetta quando la selezione della connessione MSSQL cambia."""
        self.set_led_colorMSSQL("gray")
        self.label_led_MSSQL.setText(self.tr("Seleziona e connetti"))
        # Rimuove i parametri salvati internamente per forzare la riconnessione
        if hasattr(self, '_mssql_conn_params'):
            del self._mssql_conn_params

        # Aggiorna il tooltip con i dettagli della connessione selezionata
        connection_name = self.comboBox_ConnessioneMSSQL.currentText()
        if connection_name:
            s = QSettings()
            s.beginGroup(f"MSSQL/connections/{connection_name}")
            host = s.value("host", "N/A")
            db = s.value("database", "N/A")
            # 1. Leggi il valore grezzo (restituirà "" se vuoto)
            user = s.value("username")
    
            # 2. Controllo manuale: se user è None o stringa vuota, sostituiscilo
            if not user:
                user = "Trusted Connection"
            s.endGroup()
            
            # Formattazione HTML per il tooltip
            tooltip_text = (f"<b>Connection:</b> {connection_name}<br>"
                            f"<b>Host:</b> {host}<br>"
                            f"<b>Database:</b> {db}<br>"
                            f"<b>User:</b> {user}")
            self.comboBox_ConnessioneMSSQL.setToolTip(tooltip_text)
        else:
            self.comboBox_ConnessioneMSSQL.setToolTip("")

    def reset_ui_on_connection_change_PostgreSQL(self):
        """Resetta il LED e l'etichetta quando la selezione della connessione MSSQL cambia."""
        self.set_led_colorPostgreSQL("gray")
        self.label_led_PostgreSQL.setText(self.tr("Seleziona e connetti"))
        # Rimuove i parametri salvati internamente per forzare la riconnessione
        if hasattr(self, '_postgresql_conn_params'):
            del self._postgresql_conn_params
        
        # Aggiorna il tooltip con i dettagli della connessione selezionata
        connection_name = self.comboBox_ConnessionePostgreSQL.currentText()
        if connection_name:
            s = QSettings()
            s.beginGroup(f"PostgreSQL/connections/{connection_name}")
            host = s.value("host", "N/A")
            db = s.value("database", "N/A")
            user = s.value("username", "N/A")
            port = s.value("port", "N/A")
            s.endGroup()
            
            tooltip_text = (f"<b>Connection:</b> {connection_name}<br>"
                            f"<b>Host:</b> {host}<br>"
                            f"<b>Database:</b> {db}<br>"
                            f"<b>User:</b> {user}<br>"
                            f"<b>Port:</b> {port}")
            self.comboBox_ConnessionePostgreSQL.setToolTip(tooltip_text)
        else:
            self.comboBox_ConnessionePostgreSQL.setToolTip("")

    #popola le combo box con le connessioni esistenti per MSSQL e PostgreSQL

    def populate_connection_combo_MSSQL(self): #popola la combo box con le connessioni esistenti
        self.comboBox_ConnessioneMSSQL.clear()  # pulisce la combo box
        settings = QSettings() 
        settings.beginGroup('MSSQL/connections')
        connections = settings.childGroups()
        self.comboBox_ConnessioneMSSQL.addItems(connections)

    def populate_connection_combo_PostgreSQL(self): #popola la combo box con le connessioni esistenti
        self.comboBox_ConnessionePostgreSQL.clear()  # pulisce la combo box
        settings = QSettings()
        settings.beginGroup('PostgreSQL/connections')
        connections = settings.childGroups()
        self.comboBox_ConnessionePostgreSQL.addItems(connections)

    #apre la finestra di dialogo per creare una nuova connessione per MSSQL e PostgreSQL
    
    def create_new_connection_MSSQL(self): 
        self.iface.openDataSourceManagerPage("mssql")    
        self.close()

    def create_new_connection_PostgreSQL(self): 
        self.iface.openDataSourceManagerPage("postgres")    
        self.close()

    #######################################################
    #funzioni per importare file IFC in MSSQL

    #Prendi i parametri della connessione selezionata MSSQL---------------------------------------------

    def connect_selected_DB_MSSQL(self):
        selected_connection = self.comboBox_ConnessioneMSSQL.currentText()
        if hasattr(self, '_mssql_conn_params'): del self._mssql_conn_params

        if not selected_connection:
            self.set_led_colorMSSQL("gray")
            self.label_led_MSSQL.setText(self.tr("Nessuna connessione selezionata"))
            return

        settings = QSettings()
        settings.beginGroup(f"MSSQL/connections/{selected_connection}")
        host = settings.value("host")
        database = settings.value("database")
        username = settings.value("username")
        password = settings.value("password")
        settings.endGroup()

        if not host or not database:
            self.set_led_colorMSSQL("#fa3e3e")
            self.label_led_MSSQL.setText(self.tr("Parametri mancanti"))
            return

        # UI: Connessione in corso...
        self.set_led_colorMSSQL("#ffd700") # Giallo/Oro
        self.label_led_MSSQL.setText(self.tr("Connessione in corso..."))
        self.pushButton_ConnettiMSSQL.setEnabled(False) # Disabilita per evitare doppi click

        # Avvio Thread
        self.ms_thread = MssqlConnectionThread(host, database, username, password)
        self.ms_thread.success.connect(self.on_mssql_connected)
        self.ms_thread.error.connect(self.on_mssql_error)
        self.ms_thread.start()

    def on_mssql_connected(self, params):
        self._mssql_conn_params = params
        self.set_led_colorMSSQL("#90ee90")
        self.label_led_MSSQL.setText(self.tr("Connesso"))
        self.pushButton_ConnettiMSSQL.setEnabled(True)

    def on_mssql_error(self, err_msg):
        self.set_led_colorMSSQL("#fa3e3e")
        self.label_led_MSSQL.setText(self.tr("Connessione fallita"))
        self.pushButton_ConnettiMSSQL.setEnabled(True)
        QMessageBox.warning(self, self.tr("Errore MSSQL"), self.tr("Impossibile raggiungere il database.\n\nDettaglio:\n{err}").format(err=err_msg))
    # Funzione controllo georeferenziazione

    @staticmethod
    def verifica_georeferenziazione_ifc(file_path):
        """
        Verifica che il file IFC contenga le classi IFCMAPCONVERSION e IFCPROJECTEDCRS
        e che i campi minimi necessari (Eastings, Northings per MapConversion e Name per CRS)
        siano compilati e non siano nulli ($).
        """
        has_valid_crs = False
        has_valid_map_conversion = False
        
        # Regex per IFCPROJECTEDCRS; Cerca: IFCPROJECTEDCRS('Nome', ...); Verifica che il primo parametro (Nome) sia una stringa tra apici e non vuota/nulla
        regex_crs = re.compile(r"IFCPROJECTEDCRS\s*\(\s*'[^']+'", re.IGNORECASE)

        # Regex per IFCMAPCONVERSION; Cerca: IFCMAPCONVERSION(Source, Target, Easting, Northing, ...); Estrae i gruppi 3 (Easting) e 4 (Northing) per verificare che siano numeri e non '$'
        regex_map = re.compile(r"IFCMAPCONVERSION\s*\(\s*[^,]+\s*,\s*[^,]+\s*,\s*([^,]+)\s*,\s*([^,]+)", re.IGNORECASE)

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Ottimizzazione: se abbiamo già trovato entrambi, usciamo dal loop
                    if has_valid_crs and has_valid_map_conversion:
                        return True

                    # Controllo IFCPROJECTEDCRS
                    if not has_valid_crs:
                        if "IFCPROJECTEDCRS" in line:
                            if regex_crs.search(line):
                                has_valid_crs = True

                    # Controllo IFCMAPCONVERSION
                    if not has_valid_map_conversion:
                        if "IFCMAPCONVERSION" in line:
                            match = regex_map.search(line)
                            if match:
                                easting = match.group(1).strip()
                                northing = match.group(2).strip()
                                # Verifica che est e nord non siano '$' (null) e siano numerici
                                if easting != '$' and northing != '$':
                                    has_valid_map_conversion = True
            
            # Ritorna True solo se entrambi sono stati trovati e validati
            return has_valid_crs and has_valid_map_conversion

        except Exception as e:
            print(f"Errore durante la lettura del file per validazione GEO: {e}")
            return False


    # Funzione per estrarre il nome interno del progetto IFC

    @staticmethod
    def estrai_nome_interno_ifc(file_path):
        """
        Estrae il nome interno del progetto dall'header del file IFC.
        Cerca la stringa: FILE_NAME('NomeInterno.ifc', ...);
        """
        nome_interno = None
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Cerca l'inizio della sezione FILE_NAME
                    if "FILE_NAME" in line:
                        # Regex: Cerca FILE_NAME, parentesi aperta, spazi opzionali, apice, (il contenuto che vogliamo), apice.
                        match = re.search(r"FILE_NAME\s*\(\s*'([^']+)'", line)
                        if match:
                            nome_interno = match.group(1)
                            break
                    
                    # Se arriviamo alla sezione DATA, fermiamoci per efficienza
                    if "DATA;" in line:
                        break
        except Exception as e:
            print(f"Errore estrazione nome interno: {e}")
        
        # Se non trova nulla, ritorna None
        return nome_interno



    # Funzione per scegliere il file IFC MSSQL----------------------------------------------------------

    def scegli_file_ifc_MSSQL(self): 
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Seleziona un file IFC"),
            "",
            "IFC files (*.ifc);;All files (*)"
        )

        if file_path:
            # --- 1 VERIFICA GEOREFERENZIAZIONE ---
            self.log_info(f"Verifica georeferenziazione per: {os.path.basename(file_path)}...")
            
            is_georeferenced = self.verifica_georeferenziazione_ifc(file_path)
            
            if not is_georeferenced:
                error_msg = self.tr("Il file selezionato NON contiene informazioni di georeferenziazione valide.\n\nMancano o sono incompleti:\n- IFCPROJECTEDCRS (Nome CRS)\n- IFCMAPCONVERSION (Coordinate Est/Nord)\n\nL'importazione è stata annullata per questo file.")
                QMessageBox.warning(self, self.tr("Errore Georeferenziazione"), error_msg)
                
                # Resetto la selezione interna se c'era
                self.selected_ifc = None 
                return
    
            # 2. CONTROLLO NOME INTERNO vs ESTERNO (Strict Mode)
            nome_interno = self.estrai_nome_interno_ifc(file_path)
            nome_esterno = os.path.basename(file_path)

            # Caso A: Nome interno non trovato
            if not nome_interno:
                error_msg = (self.tr("Impossibile leggere il nome interno (FILE_NAME) nell'header del file IFC.\n\nIl file potrebbe essere corrotto o non standard.\nProcedura annullata."))
                QMessageBox.critical(self, self.tr("Errore: Nome Interno Mancante"), error_msg)
                self.selected_ifc = None
                return

            # Caso B: Mismatch tra i nomi
            if nome_interno != nome_esterno:
                error_msg = self.tr(
                "ERRORE DI VALIDAZIONE NOME FILE\n\nIl nome del file fisico ('{nome_esterno}') NON corrisponde al nome interno dichiarato nell'header IFC ('{nome_interno}').\n\nPer evitare errori nel database, è obbligatorio che i due nomi coincidano.\nRinomina il file o modifica l'header IFC e riprova."
                ).format(nome_esterno=nome_esterno, nome_interno=nome_interno)
                
                QMessageBox.critical(self, self.tr("Errore: Nomi Diversi"), error_msg)
                self.selected_ifc = None
                return

            # Se arriviamo qui, i nomi sono IDENTICI.
            # Possiamo procedere sicuri.
            self.selected_ifc = file_path 
            
            self.log_info(f"File validato e selezionato: {nome_esterno}")
            QMessageBox.information(self, self.tr("File selezionato"), 
                                    self.tr("Hai selezionato il file:\n{nome_esterno}").format(nome_esterno=nome_esterno))



    
    # Insieme delle funzioni per importare il file IFC MSSQL----------------------------------------------------------

    # Funzione per identificare la versione dello schema IFC (IFC4 vs IFC4x3)
    @staticmethod
    def identify_ifc_version(file_path): 
        """
        Legge l'header del file IFC per determinare se è IFC4 o IFC4x3.
        Ritorna "IFC4", "IFC4X3" o None/Altro.
        """
        schema = None
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in range(100): # Legge solo le prime 100 righe per velocità
                    line = f.readline()
                    if "FILE_SCHEMA" in line:
                        # Esempio: FILE_SCHEMA(('IFC4'));
                        clean_line = line.upper().replace(" ", "").replace("'", "").replace('"', "")
                        if "IFC4X3" in clean_line:
                            return "IFC4X3"
                        elif "IFC4" in clean_line:
                            return "IFC4"
                        elif "IFC2X3" in clean_line:
                            return "IFC2X3"
        except Exception as e:
            print(f"Errore lettura header: {e}")
        return schema
    
    # Funzione per verificare se il file esiste già nel database MSSQL
    
    def verifica_file_esistente_db(self, host, database, username, password, file_name):
        try:
            # Costruzione stringa connessione
            conn_str_parts = [
                "DRIVER={ODBC Driver 17 for SQL Server}",
                f"SERVER={host}",
                f"DATABASE={database}",
                "TrustServerCertificate=yes"
            ]

            # Gestione AUTENTICAZIONE
            if username and str(username).strip() != "":
                conn_str_parts.append(f"UID={username}")
                conn_str_parts.append(f"PWD={password}")
            else:
                conn_str_parts.append("Trusted_Connection=yes")

            connection_string = ";".join(conn_str_parts)

            # Connessione e Query
            conn = pyodbc.connect(connection_string, timeout=15)
            cursor = conn.cursor()

            query = "SELECT COUNT(*) FROM ifcProject.Project WHERE ProjectName = ?"
            cursor.execute(query, (file_name,))
            
            # fetchval() recupera il primo valore della prima riga in modo efficiente
            count = cursor.fetchval() 
            
            conn.close()

            if count > 0:
                return True
            else:
                return False

        except Exception as e:
            # Se la connessione fallisce qui, logghiamo l'errore e ritorniamo True (blocchiamo l'importazione per sicurezza)
            self.log_error(f"Errore durante la verifica pre-importazione: {str(e)}")

            # Mostra errore specifico all'utente se la verifica fallisce
            msg_box = self.tr("Impossibile verificare i duplicati:\n{0}").format(e=str(e))
            QMessageBox.critical(self, self.tr("Errore Database"), msg_box)

            return True # Blocca l'importazione

    def esegui_importazione_exe(self, file_path, server_host, schema_version, progress_dialog):
        """
        Lancia gli eseguibili precompilati (Import_IFC4.exe o Import_IFC4X3.exe)
        presenti nella cartella IfcSQL del plugin.
        """
        # 1. Determina percorsi
        plugin_dir = os.path.dirname(__file__)
        exe_folder = os.path.join(plugin_dir, "IfcSQL Script")
        
        exe_name = ""
        if schema_version == "IFC4":
            exe_name = "Import_IFC4.exe"
        elif schema_version == "IFC4X3":
            exe_name = "Import_IFC4X3.exe"
        else:
            raise Exception(self.tr("Versione schema non supportata dagli eseguibili: {schema_version}").format(schema_version=schema_version))
        
        exe_path = os.path.join(exe_folder, exe_name)

        # Verifica esistenza file
        if not os.path.exists(exe_path):
            raise Exception(self.tr("Eseguibile non trovato:\n{exe_path}\nControlla l'installazione del plugin.").format(exe_path=exe_path))

        # Configurazione Subprocess
        # Comando: [PercorsoEXE, PercorsoIFC, ServerString]
        # Nota: L'eseguibile assume il nome DB "ifcSQL" e auth integrata o stringa server standard.
        cmd = [exe_path, file_path, server_host]

        self.log_info(f"Avvio EXE: {exe_name}")
        self.log_info(f"Server Target: {server_host}")

        progress_dialog.setValue(50)
        progress_dialog.setLabelText(self.tr("Importazione in corso con {exe_name}...\nL'operazione potrebbe richiedere alcuni minuti.").format(exe_name=exe_name))
        QApplication.processEvents()

        # Impostazioni per nascondere la finestra console su Windows
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            # Esecuzione
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=HIDE_WINDOW_FLAGS # Usa la flag globale definita all'inizio del file
            )

            # Analisi Output
            if process.returncode == 0:
                self.log_info("Processo EXE terminato con successo.")
                self.log_info(f"Output: {process.stdout}")
                progress_dialog.setValue(90)
            else:
                # Errore nell'EXE
                err_msg = process.stderr if process.stderr else process.stdout
                raise Exception(self.tr("Il processo di importazione ha restituito un errore:\n\n{err_msg}").format(err_msg=err_msg))

        except subprocess.CalledProcessError as e:
            raise Exception(self.tr("Errore esecuzione subprocess:\n{e}").format(e=str(e)))
        

    # Funzione principale per importare il file IFC------------------------------------------------

    def import_ifc_file_MSSQL(self):
        # 1. Verifica Selezione File
        if not hasattr(self, 'selected_ifc') or not self.selected_ifc:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Devi prima selezionare un file IFC!"))
            return

        file_path = self.selected_ifc
        file_name_original = os.path.basename(file_path)
        file_name = file_name_original.replace(" ", "")  # Rimuove spazi per coerenza

        # 2. Verifica Parametri DB
        if not hasattr(self, '_mssql_conn_params'):
            QMessageBox.warning(self, self.tr("Errore"), self.tr("Devi prima connettere il database selezionato."))
            return

        conn_params = self._mssql_conn_params
        host, database, username, password = conn_params

        # === START PROGRESS DIALOG ===
        progress = QProgressDialog(self.tr("Avvio procedura..."), self.tr("Annulla"), 0, 100, self)
        progress.setWindowTitle(self.tr("Importazione IFC"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None) 
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        try:
            # 3. VERIFICA ESISTENZA FILE NEL DB 
            progress.setValue(10)
            progress.setLabelText(self.tr("Verifica esistenza file nel DB..."))
            QApplication.processEvents()
            
            # Passiamo anche la porta alla funzione
            esiste = self.verifica_file_esistente_db(host, database, username, password, file_name)
            
            if esiste:
                progress.close()
                QMessageBox.warning(self, self.tr("File Duplicato"), 
                    self.tr("Il file '{file_name}' risulta già presente nel database (tabella ifcProject.Project).\n\nImportazione annullata per evitare duplicati.").format(file_name=file_name))
                return

            # 4. Rilevamento Schema (IFC4 vs IFC4x3)
            progress.setValue(20)
            progress.setLabelText(self.tr("Analisi versione IFC..."))
            QApplication.processEvents()
            
            schema_version = self.identify_ifc_version(file_path)
            
            if schema_version == "IFC2X3":
                progress.close()
                QMessageBox.warning(self, self.tr("Formato non supportato"), self.tr("I file IFC2x3 sono ignorati da questo strumento."))
                return
            elif schema_version not in ["IFC4", "IFC4X3"]:
                progress.close()
                QMessageBox.critical(self, self.tr("Errore Schema"), self.tr("Impossibile determinare una versione supportata (IFC4 o IFC4x3).\nRilevato: {schema_version}").format(schema_version=schema_version))
                return
            
            self.log_info(f"Versione IFC rilevata: {schema_version}")

            # 5. Esecuzione Importazione EXE
            progress.setValue(30)
            # Chiamata alla funzione che gestisce l'EXE esterno
            self.esegui_importazione_exe(file_path, host, schema_version, progress)

            # 6. Successo
            progress.setValue(100)
            progress.setLabelText(self.tr("Operazione completata."))
            QApplication.processEvents()
            time.sleep(1)

            progress.close()
            QMessageBox.information(self, self.tr("Completato"), self.tr("Importazione del file {schema_version} completata con successo.").format(schema_version=schema_version))

        except Exception as e:
            # === GESTIONE ERRORI ===
            progress.close()
            self.log_error(f"Errore critico durante l'importazione:\n{str(e)}")
            
            QMessageBox.critical(self, self.tr("Errore nell'importazione"), 
                self.tr("L'operazione è stata interrotta. \n\nDettaglio: {e}").format(e=str(e)))


    





#    ██ ███    ███ ██████   ██████  ██████  ████████     ██████   ██████  ███████ ████████  ██████  ██████  ███████ ███████ 
#    ██ ████  ████ ██   ██ ██    ██ ██   ██    ██        ██   ██ ██    ██ ██         ██    ██       ██   ██ ██      ██      
#    ██ ██ ████ ██ ██████  ██    ██ ██████     ██        ██████  ██    ██ ███████    ██    ██   ███ ██████  █████   ███████ 
#    ██ ██  ██  ██ ██      ██    ██ ██   ██    ██        ██      ██    ██      ██    ██    ██    ██ ██   ██ ██           ██ 
#    ██ ██      ██ ██       ██████  ██   ██    ██        ██       ██████  ███████    ██     ██████  ██   ██ ███████ ███████ 
#                                                                                                                           
#                                                                                                                           






    #######################################################
    #######################################################
    #funzioni per importare file IFC in PostgreSQL
    ######################################################

    #prendi i parametri della connessione selezionata PostgreSQL---------------------------------------------

    def connect_selected_DB_PostgreSQL(self):
        selected_connection = self.comboBox_ConnessionePostgreSQL.currentText()
        if hasattr(self, '_postgresql_conn_params'): del self._postgresql_conn_params

        if not selected_connection:
            self.set_led_colorPostgreSQL("gray")
            self.label_led_PostgreSQL.setText(self.tr("Nessuna connessione selezionata"))
            return

        settings = QSettings()
        settings.beginGroup(f"PostgreSQL/connections/{selected_connection}")
        host = settings.value("host")
        database = settings.value("database")
        username = settings.value("username")
        password = settings.value("password")
        port = settings.value("port", type=int) 
        settings.endGroup()

        if not host or not database or not username or port == 0:
            self.set_led_colorPostgreSQL("#fa3e3e")
            self.label_led_PostgreSQL.setText(self.tr("Parametri mancanti"))
            return

        # UI: Connessione in corso...
        self.set_led_colorPostgreSQL("#ffd700") # Giallo/Oro
        self.label_led_PostgreSQL.setText(self.tr("Connessione in corso..."))
        self.pushButton_ConnettiPostgreSQL.setEnabled(False)

        # Avvio Thread
        self.pg_thread = PostgresConnectionThread(host, database, username, password, port)
        self.pg_thread.success.connect(self.on_pg_connected)
        self.pg_thread.error.connect(self.on_pg_error)
        self.pg_thread.start()

    def on_pg_connected(self, params):
        self._postgresql_conn_params = params
        self.set_led_colorPostgreSQL("#90ee90")
        self.label_led_PostgreSQL.setText(self.tr("Connesso"))
        self.pushButton_ConnettiPostgreSQL.setEnabled(True)

    def on_pg_error(self, err_msg):
        self.set_led_colorPostgreSQL("#fa3e3e")
        self.label_led_PostgreSQL.setText(self.tr("Connessione fallita"))
        self.pushButton_ConnettiPostgreSQL.setEnabled(True)
        QMessageBox.warning(self, self.tr("Errore PostgreSQL"), self.tr("Impossibile raggiungere il database.\n\nDettaglio:\n{err}").format(err=err_msg))
   
   
    # Funzione per scegliere il file IFC per inserirlo in PostgreSQL----------------------------------------------------------

    def scegli_file_ifc_PostgreSQL(self): 
        # Legge il percorso di MSSQL. 
        # L'aggiunta di 'or ""' garantisce che se self.selected_ifc è None, diventi una stringa vuota
        percorso_iniziale = getattr(self, 'selected_ifc', "") or ""
        

        file_path_PostgreSQL, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Seleziona un file IFC"),
            percorso_iniziale,
            "IFC files (*.ifc);;All files (*)"
        )


        if file_path_PostgreSQL:
            # CONTROLLO NOME INTERNO vs ESTERNO
            nome_interno = self.estrai_nome_interno_ifc(file_path_PostgreSQL)
            nome_esterno = os.path.basename(file_path_PostgreSQL)

            # Caso A: Non trovato
            if not nome_interno:
                QMessageBox.critical(self, self.tr("Errore"), self.tr("Impossibile leggere il nome interno (FILE_NAME) nel file IFC."))
                self.selected_ifc_PostgreSQL = None
                return

            # Caso B: Mismatch
            if nome_interno != nome_esterno:
                error_msg = self.tr(
                    "Discrepanza rilevata!\n\n"
                    "Nome File: {nome_esterno}\n"
                    "Nome Interno: {nome_interno}\n\n"
                    "I nomi devono coincidere per procedere."
                ).format(nome_esterno=nome_esterno, nome_interno=nome_interno)

                QMessageBox.critical(self, self.tr("Errore Nomi"), error_msg)
                self.selected_ifc_PostgreSQL = None
                return

            # Validazione OK
            self.selected_ifc_PostgreSQL = file_path_PostgreSQL
            QMessageBox.information(self, self.tr("File selezionato"), self.tr("Hai selezionato il file:\n{nome_esterno}").format(nome_esterno=nome_esterno))
        
     
            
            



    # Funzione per controllare se il progetto esiste già in PostgreSQL o in MSSQL prima di importarlo

    def handle_importa_postgres_click(self):
        
        # 1. Verifica che un file sia stato selezionato
        if not hasattr(self, 'selected_ifc_PostgreSQL') or not self.selected_ifc_PostgreSQL:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Devi prima selezionare un file IFC!"))
            return

        # 2. Verifica che i parametri di connessione esistano
        if not hasattr(self, '_postgresql_conn_params'):
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Devi prima connetterti al database (Premi 'Connetti')."))
            return

        # Recupera il nome del file COMPLETO di estensione (es. "progetto.ifc")
        project_name_original = os.path.basename(self.selected_ifc_PostgreSQL)

        # Pulisce il nome del progetto rimuovendo spazi
        project_name = project_name_original.replace(" ", "")  # Sostituisce spazi con nulla

        # Recupera parametri connessione
        host, dbname, user, password, port = self._postgresql_conn_params
        db_params = {
            "host": host, "dbname": dbname, "user": user, "password": password, "port": port
        }

        conn = None
        try:
            # 3. Connessione temporanea per i controlli
            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()

            # CONTROLLO A: Il progetto esiste già in PostgreSQL?
            # Verifica su ifcproject.projectpostgres colonna ProjectName
            query_check_pg = """
                SELECT 1 FROM ifcproject.projectpostgres 
                WHERE "ProjectName" = %s 
                LIMIT 1
            """
            cursor.execute(query_check_pg, (project_name,))
            if cursor.fetchone():
                QMessageBox.warning(self, self.tr("Operazione Interrotta"), 
                                    self.tr("Il progetto '{project_name}' risulta già presente in PostgreSQL.\n\nImportazione annullata per evitare duplicati.").format(project_name=project_name))
                return # Interrompe tutto

            # CONTROLLO B: Il progetto esiste in MSSQL?
            # Verifica su ifcproject.project (Foreign Table) colonna ProjectName
            query_check_mssql = """
                SELECT "ProjectId" FROM ifcproject.project 
                WHERE "ProjectName" = %s 
                LIMIT 1
            """
            cursor.execute(query_check_mssql, (project_name,))
            result = cursor.fetchone()

            if not result:
                QMessageBox.warning(self, self.tr("Operazione Interrotta"), 
                                    self.tr("Il progetto '{project_name}' NON è stato trovato in MSSQL.\n\nImportalo prima in MSSQL.").format(project_name=project_name))
                return # Interrompe tutto
            
            # Se siamo qui, abbiamo il ProjectId corretto associato a quel nome file
            project_id = result[0]
            
            # Avvia la procedura di importazione passando ID e Nome esatti
            self.import_ifc_file_PostgreSQL(project_id, project_name)

        except psycopg2.Error as e:
            QMessageBox.critical(self, self.tr("Errore Database"), self.tr("Impossibile eseguire i controlli sul DB:\n{error}").format(error=e))
        finally:
            if conn:
                conn.close()

    #Funzione per trasformare gli elementi IFC in OBJ

    @staticmethod
    def convert_ifc_to_obj(ifc, elements, space, ifcconvert_path, output_dir, progress_dialog, original_ifc_path):
        """
        Converte tutti gli IfcElement e IfcSpace da un file IFC in file OBJ separati.
        """
        
        log_report = [] # Qui salviamo i messaggi per l'utente
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "Trovati {numero_elements} IfcElement e {numero_space} IfcSpace.\n").format(numero_elements=len(elements), numero_space=len(space)))

        # Contatore per la barra di avanzamento
        current_step = 0 
        operation_aborted = False

        # Inizializzazione contatori ### ---
        success_count = 0   # Elementi convertiti correttamente
        failed_count = 0    # Elementi che hanno generato errore
        skipped_count = 0   # Elementi saltati 

        # Controlla duplicati
        global_ids = [el.GlobalId for el in elements]
        duplicates = set([gid for gid in global_ids if global_ids.count(gid) > 1])
        if duplicates:
            log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "ATTENZIONE: Trovati elementi duplicati (GlobalId): {GID_duplicates}\n").format(GID_duplicates=duplicates))
        
        skip_types = {"IfcOpeningElement"}
        
        # --- Ciclo per gli IfcElement ---
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "\n---- Conversione IfcElement ----\n"))
        
        for idx, element in enumerate(elements, start=1):
            
            #serve per aggiornare la barra di avanzamento
            current_step += 1
            progress_dialog.setValue(current_step)

            # Controlla se l'utente ha cliccato "Annulla"
            if progress_dialog.wasCanceled():
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "OPERAZIONE ANNULLATA DALL'UTENTE"))
                operation_aborted = True
                break # Esce dal ciclo for
            
            # Salta i tipi da escludere
            if element.is_a() in skip_types:
                skipped_count += 1
                continue
            
            # Costruisci i nomi dei file usando element number, class name, e GlobalId
            class_name = element.is_a()
            obj_filename = f"{idx}_{class_name}_{element.GlobalId}.obj"
            
            # Percorso output OBJ
            temp_obj_path = os.path.join(output_dir, obj_filename)
            
            # CONVERSIONE PARTENDO DA UN FILE IFC COMPLETO ORIGINALE
            command = [
                ifcconvert_path,
                original_ifc_path,      # File IFC COMPLETO originale
                temp_obj_path,          # Output OBJ
                "--include",            # Filtro
                "attribute", 
                "GlobalId", 
                element.GlobalId
            ]

            success = False
            try:
                # Usiamo capture_output per intercettare gli errori
                subprocess.run(command, check=True, capture_output=True, text=True, creationflags=HIDE_WINDOW_FLAGS)
                success = True
            except subprocess.CalledProcessError as e:
                # Se IfcConvert fallisce, scrive l'errore nel report
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "ERRORE (IfcConvert): {errore}").format(errore=e.stderr))
            
            #Registra il fallimento nel log, se la conversione non è riuscita
            if success:
                success_count += 1
            else:
                failed_count += 1
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "Conversione fallita per: {element_GID}\n").format(element_GID=element.GlobalId))

        # Se annullato, ritorna subito False
        if operation_aborted:
            return False, log_report

        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "Riepilogo Conversione IfcElement:"))
        nomi_esclusi = ", ".join(sorted(skip_types))
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "- Convertiti: {success_count} \n- Esclusi: {skipped_count} ({nomi_esclusi}) \n- Falliti: {failed_count}. \n").format(success_count=success_count, skipped_count=skipped_count, nomi_esclusi=nomi_esclusi, failed_count=failed_count))

        # Inizializza contatori per gli IfcSpace
        space_success_count = 0
        space_failed_count = 0

        # --- Ciclo per gli IfcSpace ---
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "\n---- Conversione IfcSpace ----\n"))

        for idx, sp in enumerate(space, start=1):

            #aggiornare la barra di avanzamento
            current_step += 1
            progress_dialog.setValue(current_step)

            # Controlla se l'utente ha cliccato "Annulla"
            if progress_dialog.wasCanceled():
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "OPERAZIONE ANNULLATA DALL'UTENTE"))
                operation_aborted = True
                break # Esce dal ciclo for

            # Costruisci i nomi dei file usando element number, class name, e GlobalId
            class_name = sp.is_a()
            obj_filename = f"{idx}_{class_name}_{sp.GlobalId}.obj"
            # Percorso output OBJ
            temp_obj_path = os.path.join(output_dir, obj_filename)

            command = [
                ifcconvert_path,
                original_ifc_path,      # File ORIGINALE
                temp_obj_path,          # Output
                "--include",            # Filtro
                "attribute", 
                "GlobalId", 
                sp.GlobalId,
                "--exclude", "entities", "IfcOpeningElement" # Esclude IfcOpeningElement ma non IFCSPACE
            ]

            success = False
            try:
                subprocess.run(command, check=True, capture_output=True, text=True, creationflags=HIDE_WINDOW_FLAGS)
                success = True
            except subprocess.CalledProcessError as e:
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "ERRORE (IfcConvert): {errore}").format(errore=e.stderr))
            
            #Registra il fallimento nel log, se la conversione non è riuscita
            if success:
                space_success_count += 1
            else:
                space_failed_count += 1
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "Conversione fallita per: {element_GID}\n").format(element_GID=sp.GlobalId))

        if operation_aborted:
            return False, log_report
        
        # --- Riepilogo immediato Space ---
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "Riepilogo Conversione IfcSpace:"))
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "- Convertiti: {success_count}\n- Falliti: {failed_count}.\n").format(success_count=space_success_count, failed_count=space_failed_count))

        # --- Riepilogo finale ---
        obj_files = [f for f in os.listdir(output_dir) if f.lower().endswith('.obj')] # Conta gli elementi convertiti in OBJ
        converted_ids = {f.split('_', 2)[-1][:-4] for f in obj_files} # Estrai GlobalId dagli OBJ generati (il formato è: "{idx}_{class_name}_{GlobalId}.obj"), Prende tutto dopo il secondo underscore fino a ".obj"
        
        not_converted = [
            (el.is_a(), el.GlobalId)
            for el in elements
            if el.is_a() not in skip_types and el.GlobalId not in converted_ids
        ]

        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "\n---- RIEPILOGO FINALE ----\n"))
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "Totale file OBJ creati: {obj_count}\n").format(obj_count=len(obj_files)))
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "ATTENZIONE: Alcuni elementi (esempio: IfcStair, IfcRoof, IfcCurtainWall) potrebbero non avere una propria geometria e quindi non essere convertiti.\n"))
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "IfcElement NON convertiti (esclusi {nomi_esclusi}): {not_converted_count}\n").format(nomi_esclusi=nomi_esclusi, not_converted_count=len(not_converted)))
        
        if not_converted:
            for class_name, gid in not_converted:
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "  -> Classe: {class_name}, GlobalId: {gid}\n").format(class_name=class_name, gid=gid))

        # Controlla gli IfcSpace non convertiti
        space_not_converted = [
            (sp.is_a(), sp.GlobalId)
            for sp in space
            if sp.GlobalId not in converted_ids
        ]
        log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "IfcSpace NON convertiti: {space_not_converted_count}").format(space_not_converted_count=len(space_not_converted)))
        if space_not_converted:
            for class_name, gid in space_not_converted:
                log_report.append(QCoreApplication.translate("convert_ifc_to_obj", "  -> Classe: {class_name}, GlobalId: {gid}\n").format(class_name=class_name, gid=gid))
                
        # Ritorna True (Successo) e il log
        return True, log_report
    
    # funzione per estrarre il sistema di coordinate da un file IFC----------------------------------------------------------
    @staticmethod
    def extract_IFC_CRS(ifc):
        # imposta variabili di default
        epsg_code = None
        easting = None
        northing = None
        orthogonal_height = None
        x_axis_abscissa = None
        x_axis_ordinate = None

        # Get IfcProjectedCRS entity (if it exists)
        Projected_crs = ifc.by_type("IfcProjectedCRS")
        if Projected_crs:
            crs = Projected_crs[0]
            if hasattr(crs, "Name") and crs.Name and "EPSG" in crs.Name:
                try:
                    epsg_code = int(crs.Name.split(":")[1])
                except Exception:
                    epsg_code = None

        # Get IfcMapConversion entity (if it exists)
        map_conversion = ifc.by_type("IfcMapConversion")
        if map_conversion :
            mc = map_conversion[0]
            easting = getattr(mc, "Eastings", None)
            northing = getattr(mc, "Northings", None)
            orthogonal_height = getattr(mc, "OrthogonalHeight", None)
            x_axis_abscissa = getattr(mc, "XAxisAbscissa", None)
            x_axis_ordinate = getattr(mc, "XAxisOrdinate", None)

        # Ritorna i valori estratti
        return epsg_code, easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate

    # funzione per convertire i file OBJ in WKT----------------------------------------------------------

    def convert_obj_to_wkt(self, output_dir, easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate):
        """
        Converte i file .obj in WKT 3D
        """
        
        #self.iface.messageBar().pushMessage("Info", "Conversione OBJ -> WKT 3D in corso...", level=Qgis.Info, duration=3)
        
        # Lista per i messaggi di log
        log_report = [self.tr("--- Conversione OBJ in WKT 3D ---\n")]

        # Create a dictionary to associate each (class_name, GlobalId) with its WKT
        element_wkts = {}

        # Loop through all OBJ files generated in the output folder
        obj_files = [f for f in os.listdir(output_dir) if f.lower().endswith('.obj')]

        # --- QProgressDialog per questa fase ---
        progress_dialog_wkt = QProgressDialog(
            self.tr("Conversione OBJ in WKT 3D..."), 
            self.tr("Annulla"), 
            0, 
            len(obj_files), 
            self.iface.mainWindow()
        )
        progress_dialog_wkt.setWindowModality(Qt.WindowModal)

        operation_aborted = False

        for i, filename in enumerate(obj_files):
            progress_dialog_wkt.setValue(i)
            if progress_dialog_wkt.wasCanceled():
                log_report.append(self.tr("OPERAZIONE ANNULLATA DALL'UTENTE"))
                operation_aborted = True
                break
                
            obj_file_path = os.path.join(output_dir, filename)
            
            # Extract the class name and GlobalId from the file name
            base_name = os.path.splitext(filename)[0]
            parts = base_name.split('_')
            
            if len(parts) >= 3:
                idx = parts[0]
                class_name = parts[1]
                global_id = '_'.join(parts[2:])  # join the rest as GlobalId
            elif len(parts) == 2:
                class_name, global_id = parts
            else:
                class_name, global_id = None, base_name  # fallback
            
            if class_name is None:
                log_report.append(self.tr("ATTENZIONE: Formato nome file non riconosciuto: {filename}. Saltato.").format(filename=filename))
                continue

            try:
                # Load the OBJ file into a trimesh mesh object
                mesh = trimesh.load_mesh(obj_file_path)
                
                if mesh.is_empty:
                    log_report.append(self.tr("INFO: Mesh vuoto (nessuna geometria) per {global_id}. Saltato.").format(global_id=global_id))
                    element_wkts[(class_name, global_id)] = None
                    continue

                # Extract faces and vertices
                faces = mesh.faces
                vertices = mesh.vertices
                
                # Apply rotation and translation if parameters are available
                if (
                    easting is not None and northing is not None and orthogonal_height is not None
                    and x_axis_abscissa is not None and x_axis_ordinate is not None
                ):
                    # Compute rotation angle (theta) from XAxisAbscissa and XAxisOrdinate
                    theta = atan2(x_axis_ordinate, x_axis_abscissa)
                    # Build rotation matrix around Z axis
                    rot_matrix = np.array([
                        [cos(theta), -sin(theta), 0],
                        [sin(theta),  cos(theta), 0],
                        [0,           0,          1]
                    ])
                    # Apply rotation and translation to all vertices
                    vertices = np.dot(vertices, rot_matrix.T)
                    vertices += np.array([easting, northing, orthogonal_height])
                
                # Round the vertices to the fifth decimal place
                rounded_vertices = np.round(vertices, decimals=5)
                multipolygon_coords = []
                removed_faces_count = 0
                
                for face in faces:
                    # Get the 3D coordinates of the face's vertices
                    coords = [tuple(rounded_vertices[idx]) for idx in face]
                    # Ensure at least 3 unique vertices for a valid polygon
                    if len(set(coords)) < 3:
                        removed_faces_count += 1
                        continue
                    # Close the ring if not already closed
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    # Each face is a polygon with one ring (no holes)
                    multipolygon_coords.append([coords])
                
                # Sostituisco il print con il log
                if removed_faces_count > 0:
                    log_report.append(self.tr("{filename}: Rimosse {removed_faces_count} facce degenerate.").format(filename=filename, removed_faces_count=removed_faces_count))
                
                if multipolygon_coords:
                    # Build the WKT MULTIPOLYGON Z string
                    multipolygon_wkt = "MULTIPOLYGON Z ("
                    face_strings = []
                    for poly in multipolygon_coords:
                        ring_strings = []
                        for ring in poly:
                            ring_str = ", ".join(f"{x} {y} {z}" for x, y, z in ring)
                            ring_strings.append(f"({ring_str})")
                        face_strings.append(f"({', '.join(ring_strings)})")
                    multipolygon_wkt += ", ".join(face_strings) + ")"
                    element_wkts[(class_name, global_id)] = multipolygon_wkt
                else:
                    log_report.append(self.tr("ATTENZIONE: Nessun WKT generato per {global_id} (0 facce valide).").format(global_id=global_id))
                    element_wkts[(class_name, global_id)] = None

            except Exception as e:
                log_report.append(self.tr("ERRORE (trimesh/wkt) {global_id}: {error}").format(global_id=global_id, error=str(e)))
                element_wkts[(class_name, global_id)] = None

        progress_dialog_wkt.close()

        if operation_aborted:
            return False, element_wkts, log_report

        # Clean up OBJ and MTL files if needed
        log_report.append(self.tr("Pulizia file temporanei (.obj, .mtl) eseguita."))
        for filename in os.listdir(output_dir):
            if filename.lower().endswith(('.obj', '.mtl')):
                file_path = os.path.join(output_dir, filename)
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    log_report.append(self.tr("ERRORE pulizia: Impossibile rimuovere {filename}: {error}").format(filename=filename, error=str(e)))

        # riepilogo nel log
        log_report.append(self.tr("\n\n--- Riepilogo Conversione WKT ---\n"))
        wkt_count = 0
        failed_items = [] # Lista per raccogliere solo i fallimenti

        for (class_name, global_id), wkt in element_wkts.items():
            if wkt:
                # Se il WKT è stato generato, incrementa solo il contatore
                wkt_count += 1
            else:
                # Se il WKT non è stato generato, aggiungilo alla lista dei fallimenti
                failed_items.append(self.tr("{class_name} ({global_id}): Nessun WKT generato.").format(class_name=class_name, global_id=global_id))

        # 1. Calcola il totale
        total_items = len(element_wkts)

        # 2. Inserisci il riepilogo principale IN ALTO
        #    (Il '1' lo mette dopo "--- Inizio Conversione WKT 3D ---")
        log_report.insert(1, self.tr("Conversione WKT completata: {wkt_count} su {total_items} elementi processati.\n").format(wkt_count=wkt_count, total_items=total_items))

        # 3. Aggiungi la sezione dei fallimenti ALLA FINE, solo se necessario.
        if failed_items:
            log_report.append(self.tr("\n\n--- Dettaglio Elementi non generati ({failed_count}) ---\n").format(failed_count=len(failed_items)))
            log_report.extend(failed_items)
        elif total_items > 0:
            # Questa 'else' ora ha senso, perché non è più ridondante
            log_report.append(self.tr("Tutti gli elementi sono stati convertiti con successo."))
        
        # Restituisce il dizionario WKT e il report
        return True, element_wkts, log_report
    

    # Funzione per inserire i WKT in PostgreSQL----------------------------------------------------------

    def insert_wkt_to_postgresql(self, db_params, element_wkts, epsg_code, project_id, project_name):
        """
        Inserisce le geometrie WKT in PostgreSQL usando il ProjectId e ProjectName specifici.
        """

        log_report = [self.tr("--- Inserimento in PostgreSQL ---\n")]
        conn = None
        cursor = None
        
        # Stato dell'operazione, default a False
        success = False
        
        try:
            #self.iface.messageBar().pushMessage("Info", "Connessione a PostgreSQL...", level=Qgis.Info, duration=3)
            # Connect to the PostgreSQL database
            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()
            log_report.append(self.tr("Connessione stabilita. Inserimento dati per Progetto: '{project_name}' (ID: {project_id})").format(project_name=project_name, project_id=project_id))

            # --- Recupera i mapping per QUESTO specifico ProjectId ---
            log_report.append(self.tr("Recupero mapping GlobalId per ProjectId {project_id}\n").format(project_id=project_id))

            cursor.execute("""
                SELECT 
                    t1."GlobalEntityInstanceId", 
                    t1."Value"
                FROM 
                    ifcinstance.entityattributeofstring AS t1
                JOIN 
                    ifcProject.EntityInstanceIdAssignment AS t2
                    ON t1."GlobalEntityInstanceId" = t2."GlobalEntityInstanceId"
                WHERE 
                    t2."ProjectId" = %s
            """, (project_id,))

            entity_attributes = cursor.fetchall()
            value_to_entityid = {value: entity_id for entity_id, value in entity_attributes}
            
            if not value_to_entityid:
                log_report.append(self.tr("ATTENZIONE: Nessun mapping GlobalId trovato."))

            # --- QProgressDialog per il Database ---
            total_items = len(element_wkts)
            progress_dialog_db = QProgressDialog(
                self.tr("Inserimento geometrie nel Database..."), 
                self.tr("Annulla"), 
                0, 
                total_items, 
                self.iface.mainWindow()
            )
            progress_dialog_db.setWindowModality(Qt.WindowModal)

            # --- Insert data into postgres ---
            log_report.append(self.tr("Inserimento geometrie in 'ifcgeometry.entitygeometry'\n"))
            inserted_count = 0
            skipped_count = 0
            failed_count = 0
            operation_aborted = False

            for i, ((class_name, global_id), wkt) in enumerate(element_wkts.items()):
                
                # Aggiorna progress dialog
                progress_dialog_db.setValue(i)
                if progress_dialog_db.wasCanceled():
                    log_report.append(self.tr("OPERAZIONE ANNULLATA DALL'UTENTE DURANTE INSERIMENTO DB."))
                    operation_aborted = True
                    break
                
                if wkt:
                    
                    # Trova il GlobalEntityInstanceId corrispondente
                    global_entity_instance_id = value_to_entityid.get(global_id)
                    num_triangulation = wkt.count('((')
                        
                    if epsg_code:
                        wkt_with_srid = f"SRID={epsg_code};{wkt}"
                    else:
                        wkt_with_srid = wkt

                    try:  
                        # Creiamo un punto di ripristino prima di questo inserimento
                        cursor.execute("SAVEPOINT sp_insert_row")

                        cursor.execute("""
                            INSERT INTO "ifcgeometry"."entitygeometry" 
                            ("GlobalId_IfcFile", "IfcClass", "Geometry", "Triangles", "GlobalId_MSSQL", "ProjectNumber_MSSQL", "ProjectName")
                            VALUES (%s, %s, ST_GeomFromEWKT(%s), %s, %s, %s, %s)
                        """, (global_id, class_name, wkt_with_srid, num_triangulation, global_entity_instance_id, project_id, project_name))
                        
                        # Se va bene, rilasciamo il savepoint (confermiamo questa riga)
                        cursor.execute("RELEASE SAVEPOINT sp_insert_row")
                        inserted_count += 1
                        
                    except Exception as insert_e:
                        # Se va male, torniamo al savepoint (annulliamo solo questa riga)
                        cursor.execute("ROLLBACK TO SAVEPOINT sp_insert_row")
                        log_report.append(self.tr("ERRORE inserimento {global_id}: {insert_e}\n").format(global_id=global_id, insert_e=str(insert_e)))
                        failed_count += 1
                else:
                    skipped_count += 1

            progress_dialog_db.close()

            if operation_aborted:
                conn.rollback()
                return False, log_report
            
            # --- 4. Commit e riepilogo ---
            
            conn.commit()
            
            log_report.append(self.tr("Righe inserite con successo: {inserted_count}\n").format(inserted_count=inserted_count))
            log_report.append(self.tr("Elementi saltati (senza WKT): {skipped_count}").format(skipped_count=skipped_count))
            log_report.append(self.tr("Inserimenti falliti (errore): {failed_count}\n").format(failed_count=failed_count))

            # Definiamo il successo: Solo se non ci sono stati errori di inserimento
            if failed_count == 0:
                success = True
                log_report.append(self.tr("--- Inserimento completato con SUCCESSO ---\n"))
            else:
                success = False # Segnaliamo warning all'utente
                log_report.append(self.tr("--- Inserimento completato PARZIALMENTE (con errori) ---"))
        
        except psycopg2.Error as db_err:
            log_report.append(self.tr("ERRORE DATABASE (Psycopg2): {db_err}").format(db_err=db_err))
            if conn:
                conn.rollback()
            log_report.append(self.tr("Rollback eseguito. Nessun dato è stato inserito."))
            success = False # Fallimento
        except Exception as e:
            log_report.append(self.tr("ERRORE FATALE: {e}").format(e=e))
            if conn:
                conn.rollback()
            log_report.append(self.tr("Rollback eseguito. Nessun dato è stato inserito."))
            success = False # Fallimento
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            log_report.append(self.tr("Connessione al database chiusa."))
            
        return success, log_report
    

    # funzione per controllare se le librerie necessarie sono installate

    def check_and_install_dependencies(self):
        """
        Controlla le librerie necessarie. Se mancano, chiede all'utente 
        il permesso di installarle automaticamente tramite pip.
        """

        dependencies = {
            'ifcopenshell': 'ifcopenshell',
            'trimesh': 'trimesh',
            'numpy': 'numpy',
            'psycopg2': 'psycopg2-binary', 
            'pyodbc': 'pyodbc'
        }

        missing = []
        for import_name, pip_name in dependencies.items():
            try:
                importlib.import_module(import_name)
            except ImportError:
                missing.append((import_name, pip_name))

        if not missing:
            return True

        # Prepara la stringa da inserire nel messaggio
        libs_str = "\n- ".join([p[1] for p in missing])
        
        reply = QMessageBox.question(
            self,
            self.tr("Installazione Componenti Necessari"),
            self.tr("Per eseguire questa operazione è necessario installare le seguenti librerie Python aggiuntive:\n\n- {libs_str}\n\nVuoi scaricarle e installarle automaticamente ora? (Richiede connessione internet)").format(libs_str=libs_str),
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return False

        # --- FIX FINESTRA BIANCA ---
        progress = QProgressDialog(self.tr("Avvio installazione..."), None, 0, len(missing), self)
        progress.setWindowTitle(self.tr("Installazione Librerie"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0) # Forza la finestra ad apparire IMMEDIATAMENTE
        progress.resize(450, 120)      # Diamo una dimensione dignitosa di partenza
        progress.show()
        QApplication.processEvents()   # Ordina a QGIS di disegnare i testi PRIMA di bloccarsi

        # Trova il vero eseguibile di Python
        if os.name == 'nt':
            python_exe = os.path.join(sys.exec_prefix, 'python.exe')
        else:
            python_exe = sys.executable 

        startupinfo = subprocess.STARTUPINFO()
        if os.name == 'nt':
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        for i, (import_name, pip_name) in enumerate(missing):
            # Aggiorna il testo e forza di nuovo il disegno usando .format()
            progress.setLabelText(self.tr("Download e installazione di {pip_name} in corso...\nAttendere prego, potrebbe richiedere qualche minuto.").format(pip_name=pip_name))
            QApplication.processEvents() 

            try:
                subprocess.check_call(
                    [python_exe, "-m", "pip", "install", "--user", pip_name],
                    startupinfo=startupinfo,
                    creationflags=HIDE_WINDOW_FLAGS
                )
                
                # --- FIX AGGIORNAMENTO PERCORSI PYTHON ---
                user_site = site.getusersitepackages()
                if user_site not in sys.path:
                    sys.path.append(user_site)
                
                # Svuota la cache di Python
                importlib.invalidate_caches()

                # Importa dinamicamente il modulo
                globals()[import_name] = importlib.import_module(import_name)
                
                if import_name == 'pyodbc':
                    try: globals()['pyodbc'].pooling = False
                    except Exception: pass

                # Aggiorna i flag globali
                if import_name == 'ifcopenshell': globals()['IFCOPENSHELL_PRESENTE'] = True
                elif import_name == 'trimesh': globals()['TRIMESH_PRESENTE'] = True
                elif import_name == 'numpy': globals()['NUMPY_PRESENTE'] = True
                elif import_name == 'psycopg2': globals()['PSYCOPG2_PRESENTE'] = True
                elif import_name == 'pyodbc': globals()['PYODBC_PRESENTE'] = True

            except subprocess.CalledProcessError as e:
                progress.close()
                QMessageBox.critical(self, self.tr("Errore di Installazione"), self.tr("Impossibile installare {pip_name}.\n\nDettagli errore:\n{e}").format(pip_name=pip_name, e=str(e)))
                return False
            except Exception as e:
                progress.close()
                # Se l'import fallisce per DLL mancanti o incastri di sistema, suggeriamo il riavvio
                QMessageBox.warning(self, self.tr("Installazione Riuscita ma Riavvio Necessario"), self.tr("L'installazione di {pip_name} è andata a buon fine, ma QGIS ha bisogno di essere riavviato per caricare i file correttamente.\n\nRiavvia QGIS e riprova.").format(pip_name=pip_name))
                return False

            progress.setValue(i + 1)
            QApplication.processEvents()

        progress.close()
        QMessageBox.information(self, self.tr("Installazione Completata"), self.tr("Tutte le librerie sono state installate correttamente!"))
        return True
    


    # funzione completa per importare la geometria IFC in PostgreSQL----------------------------------------------------------

    def import_ifc_file_PostgreSQL(self, project_id, project_name):
        # 1. Ottieni il percorso del file IFC
        if not hasattr(self, 'selected_ifc_PostgreSQL') or not self.selected_ifc_PostgreSQL:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Devi prima selezionare un file IFC!"))
            return

        ifc_file_path = self.selected_ifc_PostgreSQL

        # Ottiene la cartella dove risiede questo file python (la root del plugin)
        plugin_dir = os.path.dirname(__file__) 


        # 2. Percorso relativo per IfcConvert
        ifcconvert_dir = os.path.join(plugin_dir, "IfcConvert")
        ifcconvert_path = os.path.join(ifcconvert_dir, "IfcConvert.exe")

        # Se l'eseguibile non esiste, cerchiamo se c'è uno zip da estrarre
        if not os.path.exists(ifcconvert_path):
            if os.path.exists(ifcconvert_dir):
                # Cerca tutti i file .zip nella cartella IfcConvert
                zip_files = [f for f in os.listdir(ifcconvert_dir) if f.lower().endswith('.zip')]
                
                if zip_files:
                    zip_path = os.path.join(ifcconvert_dir, zip_files[0]) # Prende il primo zip trovato
                    
                    # Log per l'utente (opzionale: puoi anche mostrare un QMessageBox temporaneo)
                    self.log_info(("IfcConvert.exe non trovato. Estrazione di {zip_file} in corso..."))
                    
                    try:
                        # Estrae il contenuto dello zip nella stessa cartella
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            zip_ref.extractall(ifcconvert_dir)
                        self.log_info(("Estrazione completata con successo."))
                    except Exception as e:
                        QMessageBox.critical(
                            self, 
                            self.tr("Errore Estrazione"), 
                            self.tr("Impossibile estrarre il file zip di IfcConvert:\n{e}\n\nEstrai il file manualmente.").format(e=str(e))
                        )
                        return


        # Controllo esistenza IfcConvert
        if not os.path.exists(ifcconvert_path):
            QMessageBox.critical(
                self, 
                self.tr("Errore Configurazione"), 
                self.tr("IfcConvert non trovato!\n\nIl plugin si aspetta di trovare l'exe qui:\n{ifcconvert_path}\n\nAssicurati di avere 'IfcConvert' dentro la cartella del plugin.").format(ifcconvert_path=ifcconvert_path)
            )
            return

        # 3. Percorso relativo per output OBJ
        # Crea/Usa la cartella: CartellaPlugin/OBJ_files
        output_dir = os.path.join(plugin_dir, "OBJ_files")
        # Crea la cartella se non esiste
        os.makedirs(output_dir, exist_ok=True)

        # --- PULIZIA PRELIMINARE CARTELLA OBJ ---
        # Rimuove eventuali file residui da esecuzioni interrotte
        try:
            for filename in os.listdir(output_dir):
                file_path = os.path.join(output_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as e:
            QMessageBox.critical(
                self, 
                self.tr("Errore Pulizia"), 
                self.tr("Impossibile svuotare la cartella OBJ_files:\n{e}\n\nElimina manualmente i file nella cartella 'OBJ_files' e riprova.").format(e=e)
            )
            return # Interrompe la procedura
        
        # Controlla e installa automaticamente le librerie mancanti
        if not self.check_and_install_dependencies():
            return # Ferma l'esecuzione se l'utente annulla o se c'è un errore di installazione

        # 4. Carica il file IFC
        try:
            #self.iface.messageBar().pushMessage("Info", "Caricamento file IFC...", level=Qgis.Info, duration=3)
            ifc = ifcopenshell.open(ifc_file_path)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore"), self.tr("Impossibile aprire il file IFC:\n{e}").format(e=e))
            return
        
        # --- ESTRAZIONE DATI GEOREFERENZIAZIONE ---
        try:
            epsg_code, easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate = self.extract_IFC_CRS(ifc)
            #self.iface.messageBar().pushMessage("Info", f"Dati CRS estratti. EPSG: {epsg_code}", level=Qgis.Info, duration=4)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore"), self.tr("Impossibile estrarre i dati CRS: {e}").format(e=e))
            return
        
        # Contiamo gli elementi PRIMA di iniziare per sapere il totale
        elements = ifc.by_type("IfcElement")
        spaces = ifc.by_type("IfcSpace")
        total_steps = len(elements) + len(spaces)
        
        if total_steps == 0:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun IfcElement o IfcSpace trovato nel file IFC."))
            return

        # Nascodiamo la finestra principale per evitare che compaia tra le procedure
        self.hide()

        # Creiamo e configuriamo la QProgressDialog
        progress_dialog = QProgressDialog(
            self.tr("Conversione IFC in OBJ in corso..."), 
            self.tr("Annulla"), 
            0, 
            total_steps, 
            self.iface.mainWindow()
        )
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.show()

        # =================================
        # FASE 1: CONVERSIONE IFC -> OBJ
        # =================================
        try:
            success_obj, log_report_obj = self.convert_ifc_to_obj(
                ifc, elements, spaces, ifcconvert_path, output_dir, progress_dialog, ifc_file_path)
            # Chiudiamo la barra di avanzamento
            progress_dialog.close()

            # Mostra Riepilogo OBJ
            summary_message_OBJ = "\n".join(log_report_obj)
            msgBox_OBJ = QMessageBox(self.iface.mainWindow())
            msgBox_OBJ.setWindowTitle(self.tr("Riepilogo Conversione OBJ"))
            msgBox_OBJ.setDetailedText(summary_message_OBJ)

            if not success_obj:
                msgBox_OBJ.setText(self.tr("Conversione OBJ Interrotta o Fallita."))
                msgBox_OBJ.setIcon(QMessageBox.Critical)
                msgBox_OBJ.exec_()
                return # STOP procedura

            msgBox_OBJ.setText(self.tr("Conversione OBJ completata."))
            msgBox_OBJ.setIcon(QMessageBox.Information)
            msgBox_OBJ.setStandardButtons(QMessageBox.Ok)
            # Usiamo setDetailedText per avere un testo scrollabile
            msgBox_OBJ.setDetailedText(summary_message_OBJ)
            msgBox_OBJ.exec_()

        except Exception as e:
            progress_dialog.close()
            QMessageBox.critical(self, self.tr("Errore Critico OBJ"), self.tr("Errore durante conversione OBJ:\n{e}").format(e=e))
            self.close()
            return

        # ============================================
        # FASE 2: CONVERSIONE OBJ -> WKT
        # =============================================
        try:
            success_wkt, element_wkts, log_report_wkt = self.convert_obj_to_wkt(
                output_dir, easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate
            )
            
            summary_message_wkt = "\n".join(log_report_wkt)
            msgBox_wkt = QMessageBox(self.iface.mainWindow())
            msgBox_wkt.setWindowTitle(self.tr("Riepilogo Conversione WKT"))
            msgBox_wkt.setDetailedText(summary_message_wkt)

            if not success_wkt:
                msgBox_wkt.setText(self.tr("Conversione WKT Interrotta o Fallita."))
                msgBox_wkt.setIcon(QMessageBox.Critical)
                msgBox_wkt.exec_()
                return # STOP procedura
            
            if not element_wkts or all(v is None for v in element_wkts.values()):
                msgBox_wkt.setText(self.tr("Nessun dato WKT valido generato. Impossibile proseguire."))
                msgBox_wkt.setIcon(QMessageBox.Warning)
                msgBox_wkt.exec_()
                return # STOP procedura

            msgBox_wkt.setText(self.tr("Conversione WKT completata. {element_wkts} elementi pronti.").format(element_wkts=len(element_wkts)))
            msgBox_wkt.setIcon(QMessageBox.Information)
            msgBox_wkt.setStandardButtons(QMessageBox.Ok)
            msgBox_wkt.setDetailedText(summary_message_wkt)
            msgBox_wkt.exec_()

        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore Critico WKT"), self.tr("Errore durante conversione WKT:\n{e}").format(e=e))
            self.close()
            return

        # ========================================
        # FASE 3: INSERIMENTO POSTGRESQL
        # ========================================
        try:
            if not hasattr(self, '_postgresql_conn_params'):
                QMessageBox.critical(self, self.tr("Attenzione"), self.tr("Parametri DB persi. Riconnettiti."))
                return

            host, dbname, user, password, port = self._postgresql_conn_params
            db_params = {"host": host, "dbname": dbname, "user": user, "password": password, "port": port}
            
            success_db, log_report_db = self.insert_wkt_to_postgresql(
                db_params, element_wkts, epsg_code, project_id, project_name
            )

            summary_message_db = "\n".join(log_report_db)
            msgBox_db = QMessageBox(self.iface.mainWindow())
            msgBox_db.setWindowTitle(self.tr("Riepilogo Inserimento Database"))
            msgBox_db.setDetailedText(summary_message_db)

            if success_db:
                msgBox_db.setText(self.tr("Procedura completata con SUCCESSO."))
                msgBox_db.setIcon(QMessageBox.Information)

                self.import_completed.emit()

            else:
                msgBox_db.setText(self.tr("Procedura completata PARZIALMENTE (o interrotta).\nControlla i dettagli per gli errori."))
                msgBox_db.setIcon(QMessageBox.Warning)
            
            msgBox_db.setStandardButtons(QMessageBox.Ok)
            msgBox_db.setDetailedText(summary_message_db)
            msgBox_db.exec_()
            
            self.close()

        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore Critico DB"), self.tr("Errore durante inserimento DB:\n{e}").format(e=e))
            self.close()
            return
        

        # --- AGGIORNAMENTO MV dei progetti importati in postgres IN BACKGROUND ---
        def refresh_mv_task(params):
            try:
                conn = psycopg2.connect(
                    host=params[0], database=params[1], 
                    user=params[2], password=params[3], port=params[4]
                )
                cur = conn.cursor()
                # Usiamo CONCURRENTLY così se l'utente apre subito la Query Tab 
                # può comunque leggere i vecchi dati mentre i nuovi arrivano
                cur.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY ifcproject.projectpostgres;')
                conn.commit()
                cur.close()
                conn.close()
                QgsMessageLog.logMessage("Materialized View aggiornata con successo.", "ifcSQL", Qgis.Info)
            except Exception as e:
                QgsMessageLog.logMessage(f"Refresh MV fallito: {e}", "ifcSQL", Qgis.Critical)

        # Lancio il thread e proseguo subito alla chiusura della finestra
        if success_db:
            t = threading.Thread(target=refresh_mv_task, args=(self._postgresql_conn_params,))
            t.start()
            
        self.close()











#    ██████  ███████ ██      ███████ ████████ ███████      ██████ ██       █████  ███████ ███████ 
#    ██   ██ ██      ██      ██         ██    ██          ██      ██      ██   ██ ██      ██      
#    ██   ██ █████   ██      █████      ██    █████       ██      ██      ███████ ███████ ███████ 
#    ██   ██ ██      ██      ██         ██    ██          ██      ██      ██   ██      ██      ██ 
#    ██████  ███████ ███████ ███████    ██    ███████      ██████ ███████ ██   ██ ███████ ███████ 
#                                                                                                 
#                                                                                                 







#######################################################################
## Classe per la finestra di dialogo di eliminazione progetto IFC e la finestra seleziona progetto
#######################################################################        

class SelezionaProgettoEliminaDialog(Ui_SelezionaProgetto, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        
        # 1. Creiamo il Modello Sorgente (contiene i dati veri)
        self.source_model = QStandardItemModel()
        
        # 2. Creiamo il Modello Proxy (gestisce il filtro)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        
        # Impostiamo che il filtro non faccia distinzione tra maiuscole e minuscole
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        
        # 3. Colleghiamo la ListView al PROXY (non al source model direttamente)
        self.listView.setModel(self.proxy_model)
        self.listView.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # 4. Colleghiamo la LineEdit al filtro
        self.lineEdit.setPlaceholderText(self.tr("Scrivi qui per cercare..."))
        self.lineEdit.textChanged.connect(self.filter_projects)

    def filter_projects(self, text):
        """
        Questa funzione viene chiamata ogni volta che l'utente scrive una lettera.
        Aggiorna il filtro del proxy model.
        """
        self.proxy_model.setFilterFixedString(text)


# Questa funzione si occupa di connettersi a MSSQL e PostgreSQL per recuperare la lista dei progetti 
    def populate_list(self, mssql_conn_params, pg_conn_params):
        """
        Si connette a MSSQL per la lista progetti e a PostgreSQL per verificare lo stato di importazione.
        """
        # Unpacking parametri MSSQL
        host_ms, db_ms, user_ms, pwd_ms = mssql_conn_params
        
        # Pulisce il modello precedente
        self.source_model.clear()

        # ---------------------------------------------------------
        # FASE 1: Recupero Progetti presenti su PostgreSQL (Cache)
        # ---------------------------------------------------------
        projects_in_postgres = set()
        pg_error_occurred = False
        
        try:
            # Unpacking parametri PostgreSQL
            h_pg, db_pg, u_pg, p_pg, port_pg = pg_conn_params
            
            conn_pg = psycopg2.connect(
                host=h_pg, database=db_pg, user=u_pg, password=p_pg, port=port_pg
            )
            cur_pg = conn_pg.cursor()
            
            # Recuperiamo i nomi dei progetti dalla vista materializzata
            query_pg = 'SELECT "ProjectName" FROM ifcproject.projectpostgres'
            cur_pg.execute(query_pg)
            rows_pg = cur_pg.fetchall()
            
            # Inseriamo i nomi in un set per una ricerca veloce O(1)
            # Normalizziamo togliendo spazi per sicurezza
            for row in rows_pg:
                if row[0]:
                    projects_in_postgres.add(str(row[0]).strip())
            
            cur_pg.close()
            conn_pg.close()

        except Exception as e:
            pg_error_occurred = True
            QMessageBox.warning(self, self.tr("Warning Connessione PostgreSQL"), 
                                self.tr("Impossibile verificare lo stato di PostgreSQL.\nVerrà mostrata la lista dei progetti in MSSQL.\n\nErrore: {error}").format(error=e))

        # ---------------------------------------------------------
        # FASE 2: Recupero Progetti MSSQL e Popolamento Lista
        # ---------------------------------------------------------
        try:
            conn_str_parts = [
                "DRIVER={ODBC Driver 17 for SQL Server}",
                f"SERVER={host_ms}",
                f"DATABASE={db_ms}",
                "TrustServerCertificate=yes" 
            ]

            if user_ms and str(user_ms).strip() != "":
                conn_str_parts.append(f"UID={user_ms}")
                conn_str_parts.append(f"PWD={pwd_ms}")
            else:
                conn_str_parts.append("Trusted_Connection=yes")

            connection_string = ";".join(conn_str_parts)
            
            conn = pyodbc.connect(connection_string)
            cursor = conn.cursor()

            # Query MSSQL
            query = """
                SELECT ProjectId, ProjectName 
                FROM ifcProject.Project 
                WHERE ProjectId > 1006
                ORDER BY ProjectName ASC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()

            if not rows:
                QMessageBox.information(self, self.tr("Info"), self.tr("Nessun progetto trovato in MSSQL."))
                conn.close()
                return False
            
            # Popolamento del modello
            for row in rows:
                p_id = row.ProjectId
                p_name = row.ProjectName
                p_name_clean = str(p_name).strip()
                
                # Logica di visualizzazione stato
                status_text = ""
                
                if pg_error_occurred:
                    status_text = self.tr("(Stato PG ignoto)")
                else:
                    if p_name_clean in projects_in_postgres:
                        status_text = "(MSSQL + PostgreSQL)"
                    else:
                        status_text = self.tr("(Solo MSSQL)")

                # Testo visualizzato: "NomeProgetto (Stato)"
                display_text = f"{p_name} {status_text}"
                
                item = QStandardItem(display_text)
                
                # Salviamo l'ID nel ruolo utente (invisibile ma recuperabile)
                item.setData(p_id, Qt.UserRole)
                
                self.source_model.appendRow(item)

            conn.close()
            return True

        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore Database MSSQL"), self.tr("Errore nel recupero dei progetti:\n{error}").format(error=str(e)))
            return False


    def get_selected_project(self):
        """
        Ritorna una tupla (id_progetto, nome_progetto) dell'elemento selezionato.
        Gestisce la traduzione tra indice Proxy (visivo) e indice Source (dati).
        """
        # Otteniamo gli indici selezionati dalla VISTA (che guarda il Proxy)
        proxy_indexes = self.listView.selectedIndexes()
        
        if proxy_indexes:
            proxy_index = proxy_indexes[0] # Selezione singola
            
            # Convertiamo l'indice del Proxy nell'indice del Source Model
            source_index = self.proxy_model.mapToSource(proxy_index)
            
            # Ora usiamo l'indice sorgente per recuperare l'item dal modello sorgente
            item = self.source_model.itemFromIndex(source_index)
            
            if item:
                project_id = item.data(Qt.UserRole)
                full_text = item.text()
                project_name = full_text.split(' (')[0] 
                
                return (project_id, project_name)
        
        return None





class EliminaProgettoDialog(Ui_EliminaProgettoIFC, QMainWindow):
    
    delete_completed = pyqtSignal() # Segnale personalizzato per indicare che l'eliminazione è stata completata
    
    def __init__(self, iface):
        super().__init__()
        self.setupUi(self)
        self.iface = iface

        # Crea l'istanza del Dialog
        self.select_dialog = SelezionaProgettoEliminaDialog(self)

        # Inizializza il LED grigio
        self.set_led_color("gray")

        # Collega l'evento di cambio selezione della ComboBox
        self.comboBox_MSSQL.currentIndexChanged.connect(self.reset_ui_on_connection_change_MSSQL)
        self.comboBox_PostgreSQL.currentIndexChanged.connect(self.reset_ui_on_connection_change_PostgreSQL)
        
        # Collega i pulsanti alle funzioni di crezione nuova connessione
        self.pushButton_NuovaConnessioneMSSQL.clicked.connect(self.create_new_connection_MSSQL)
        self.pushButton_NuovaCpnnessionePostgreSQL.clicked.connect(self.create_new_connection_PostgreSQL)
        
        # Connetti i database
        self.pushButton_ConnettiDB.clicked.connect(self.connect_both_databases)

        # COLLEGA IL PULSANTE "SELEZIONA" 
        self.pushButton_SelezionaProgetto.clicked.connect(self.show_select_dialog) 
        # Collega la chiusura del dialogo di selezione alla ricezione dell'OK
        self.select_dialog.accepted.connect(self.handle_project_selected)

        ##################
        # Variabili per memorizzare la selezione corrente
        self.selected_project_id = None
        self.selected_project_name = None

        # Disabilita il tasto elimina all'inizio (si attiva solo dopo aver selezionato un progetto)
        self.pushButton_Elimina.setEnabled(False)

        # Collegamento del tasto ELIMINA alla funzione logica
        self.pushButton_Elimina.clicked.connect(self.delete_selected_project)
        ##################


    def set_led_color(self, color_name):
        palette = self.label_led.palette()
        palette.setColor(self.label_led.backgroundRole(), QColor(color_name))
        self.label_led.setAutoFillBackground(True)
        self.label_led.setPalette(palette)
        self.label_led.show()

    #resetta l'interfaccia utente quando si cambia la connessione selezionata MSSQL e PostgreSQL
    
    def reset_ui_on_connection_change_MSSQL(self):
        """Resetta il LED e l'etichetta quando la selezione della connessione MSSQL cambia."""
        self.set_led_color("gray")
        self.label_led.setText(self.tr("Seleziona e connetti"))
        # Rimuove i parametri salvati internamente per forzare la riconnessione
        if hasattr(self, '_mssql_conn_params'):
            del self._mssql_conn_params

        # --- AGGIUNTA TOOLTIP ---
        connection_name = self.comboBox_MSSQL.currentText()
        if connection_name:
            s = QSettings()
            s.beginGroup(f"MSSQL/connections/{connection_name}")
            host = s.value("host", "N/A")
            db = s.value("database", "N/A")
            user = s.value("username")
            
            if not user:
                user = "Trusted Connection"
            s.endGroup()
            
            tooltip_text = (f"<b>Connection:</b> {connection_name}<br>"
                            f"<b>Host:</b> {host}<br>"
                            f"<b>Database:</b> {db}<br>"
                            f"<b>User:</b> {user}")
            self.comboBox_MSSQL.setToolTip(tooltip_text)
        else:
            self.comboBox_MSSQL.setToolTip("")

    def reset_ui_on_connection_change_PostgreSQL(self):
        """Resetta il LED e l'etichetta quando la selezione della connessione MSSQL cambia."""
        self.set_led_color("gray")
        self.label_led.setText(self.tr("Seleziona e connetti"))
        # Rimuove i parametri salvati internamente per forzare la riconnessione
        if hasattr(self, '_postgresql_conn_params'):
            del self._postgresql_conn_params
        
        # --- AGGIUNTA TOOLTIP ---
        connection_name = self.comboBox_PostgreSQL.currentText()
        if connection_name:
            s = QSettings()
            s.beginGroup(f"PostgreSQL/connections/{connection_name}")
            host = s.value("host", "N/A")
            db = s.value("database", "N/A")
            user = s.value("username", "N/A")
            port = s.value("port", "N/A")
            s.endGroup()
            
            tooltip_text = (f"<b>Connection:</b> {connection_name}<br>"
                            f"<b>Host:</b> {host}<br>"
                            f"<b>Database:</b> {db}<br>"
                            f"<b>User:</b> {user}<br>"
                            f"<b>Port:</b> {port}")
            self.comboBox_PostgreSQL.setToolTip(tooltip_text)
        else:
            self.comboBox_PostgreSQL.setToolTip("")

    #popola le combo box con le connessioni esistenti per MSSQL e PostgreSQL

    def populate_connection_combo_MSSQL_delete(self): #popola la combo box con le connessioni esistenti
        self.comboBox_MSSQL.clear()  # pulisce la combo box
        settings = QSettings() 
        settings.beginGroup('MSSQL/connections')
        connections = settings.childGroups()
        self.comboBox_MSSQL.addItems(connections)

    def populate_connection_combo_PostgreSQL_delete(self): #popola la combo box con le connessioni esistenti
        self.comboBox_PostgreSQL.clear()  # pulisce la combo box
        settings = QSettings()
        settings.beginGroup('PostgreSQL/connections')
        connections = settings.childGroups()
        self.comboBox_PostgreSQL.addItems(connections)

    #apre la finestra di dialogo per creare una nuova connessione per MSSQL e PostgreSQL
    
    def create_new_connection_MSSQL(self): 
        self.iface.openDataSourceManagerPage("mssql")    
        self.close()

    def create_new_connection_PostgreSQL(self): 
        self.iface.openDataSourceManagerPage("postgres")    
        self.close()
    
    #funzione per verificare l'allineamento tra i due database MSSQL e PostgreSQL

    def verify_database_alignment(self):
        """
        Verifica la coerenza dei DB confrontando il GUID di MSSQL diretto
        con il GUID di MSSQL visto da PostgreSQL tramite la Foreign Table 'mssql_identity_card'.
        """

        # --- STEP A: Ottieni GUID dal MSSQL connesso direttamente (QGIS) ---
        guid_direct_mssql = None
        try:
            # Recuperiamo i parametri già salvati
            host, db, user, pwd = self._mssql_conn_params
            
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host};DATABASE={db};TrustServerCertificate=yes;"
            
            if user and str(user).strip():
                conn_str += f"UID={user};PWD={pwd};"
            else:
                conn_str += "Trusted_Connection=yes;"

            conn = pyodbc.connect(conn_str, timeout=15)
            cursor = conn.cursor()
            
            # Query diretta su MSSQL
            query_guid = "SELECT service_broker_guid FROM sys.databases WHERE name = 'ifcSQL'"
            cursor.execute(query_guid)
            row = cursor.fetchone()
            
            if row:
                # Convertiamo in stringa subito per sicurezza
                guid_direct_mssql = str(row[0])
            
            conn.close()

            if not guid_direct_mssql:
                return False, self.tr("Impossibile recuperare GUID dal DB MSSQL (ifcSQL).")

        except Exception as e:
            return False, self.tr("Errore lettura GUID MSSQL Diretto: {error}").format(error=str(e))

        # --- STEP B: Ottieni GUID MSSQL interrogando PostgreSQL ---
        guid_via_postgres = None
        try:
            h_pg, db_pg, u_pg, p_pg, port_pg = self._postgresql_conn_params
            conn_pg = psycopg2.connect(host=h_pg, database=db_pg, user=u_pg, password=p_pg, port=port_pg)
            cursor_pg = conn_pg.cursor()
            
            # Interroghiamo la tabella ponte creata dall'utente
            # Se la connessione FDW è rotta, questa query fallirà qui, dandoci l'errore corretto
            query_check = "SELECT db_guid FROM public.mssql_identity_card"
            
            cursor_pg.execute(query_check)
            row_pg = cursor_pg.fetchone()
            conn_pg.close()

            if row_pg and row_pg[0]:
                guid_via_postgres = str(row_pg[0])
            else:
                return False, self.tr("La tabella 'public.mssql_identity_card' in Postgres è vuota o non accessibile.")

        except Exception as e:
            # Questo intercetta anche errori di connessione FDW (es. Postgres non raggiunge MSSQL)
            return False, self.tr("Errore leggendo 'mssql_identity_card' da Postgres:\n\n{error}").format(error=str(e))

        # --- STEP C: Confronto (Case Insensitive) ---
        # MSSQL ritorna spesso MAIUSCOLO (es. A1B2...), Postgres UUID è minuscolo (es. a1b2...)
        
        guid_mssql_norm = guid_direct_mssql.strip().lower()
        guid_pg_norm = guid_via_postgres.strip().lower()

        if guid_mssql_norm == guid_pg_norm:
            return True, self.tr("OK")
        else:
            return False, (self.tr("DISALLINEAMENTO DATABASE!\n\n1. GUID MSSQL (QGIS): {guid_mssql_norm}\n2. GUID MSSQL (visto da PG): {guid_pg_norm}\n\nPostgreSQL è collegato (via FDW) a un database MSSQL diverso da quello selezionato qui.").format(guid_mssql_norm=guid_mssql_norm, guid_pg_norm=guid_pg_norm))



    #funzione per connettere entrambi i database MSSQL e PostgreSQL
    def connect_both_databases(self):
        """
        Avvia i thread di connessione. L'allineamento verrà fatto
        in automatico quando entrambi avranno risposto.
        """
        # Variabili per tracciare lo stato dei due thread
        self.mssql_ready = False
        self.postgres_ready = False
        self.connection_errors = []

        # UI: Connessione in corso...
        self.set_led_color("#ffd700") # Giallo/Oro
        self.label_led.setText(self.tr("Connessione in corso..."))
        self.pushButton_ConnettiDB.setEnabled(False) # Disabilita per evitare doppi click

        # Avvia i tentativi di connessione 
        self.connect_selected_DB_MSSQL()
        self.connect_selected_DB_PostgreSQL()

    # FUNZIONE connetti MSSQL 
    def connect_selected_DB_MSSQL(self):
        selected_connection = self.comboBox_MSSQL.currentText()
        if hasattr(self, '_mssql_conn_params'): del self._mssql_conn_params

        if not selected_connection:
            self.on_mssql_error(self.tr("Nessuna connessione MSSQL selezionata"))
            return

        settings = QSettings()
        settings.beginGroup(f"MSSQL/connections/{selected_connection}")
        host = settings.value("host")
        database = settings.value("database")
        username = settings.value("username")
        password = settings.value("password")
        settings.endGroup()

        if not host or not database:
            self.on_mssql_error(self.tr("Parametri MSSQL mancanti"))
            return

        self.ms_thread = MssqlConnectionThread(host, database, username, password)
        self.ms_thread.success.connect(self.on_mssql_connected)
        self.ms_thread.error.connect(self.on_mssql_error)
        self.ms_thread.start()

    # FUNZIONE connetti POSTGRESQL 
    def connect_selected_DB_PostgreSQL(self):
        selected_connection = self.comboBox_PostgreSQL.currentText()
        if hasattr(self, '_postgresql_conn_params'): del self._postgresql_conn_params

        if not selected_connection:
            self.on_pg_error(self.tr("Nessuna connessione PostgreSQL selezionata"))
            return

        settings = QSettings()
        settings.beginGroup(f"PostgreSQL/connections/{selected_connection}")
        host = settings.value("host")
        database = settings.value("database")
        username = settings.value("username")
        password = settings.value("password")
        port = settings.value("port", type=int) 
        settings.endGroup()

        if not host or not database or not username or port == 0:
            self.on_pg_error(self.tr("Parametri PostgreSQL mancanti"))
            return

        self.pg_thread = PostgresConnectionThread(host, database, username, password, port)
        self.pg_thread.success.connect(self.on_pg_connected)
        self.pg_thread.error.connect(self.on_pg_error)
        self.pg_thread.start()

    # GESTIONE RISPOSTE DEI THREAD
    def on_mssql_connected(self, params):
        self._mssql_conn_params = params
        self.mssql_ready = True
        self.check_if_both_ready()

    def on_mssql_error(self, err_msg):
        self.connection_errors.append(f"MSSQL: {err_msg}")
        self.check_if_both_ready()

    def on_pg_connected(self, params):
        self._postgresql_conn_params = params
        self.postgres_ready = True
        self.check_if_both_ready()

    def on_pg_error(self, err_msg):
        self.connection_errors.append(f"PostgreSQL: {err_msg}")
        self.check_if_both_ready()

    # PUNTO DI INCONTRO: ALLINEAMENTO database
    def check_if_both_ready(self):
        """
        Controlla se entrambi i thread hanno finito (con successo o errore).
        Se ci sono errori ferma tutto, altrimenti lancia l'allineamento.
        """
        # Controlla se abbiamo ricevuto risposta da ENTRAMBI i DB
        # (Se uno è ready o in errore + l'altro è ready o in errore)
        mssql_finished = self.mssql_ready or any("MSSQL" in e for e in self.connection_errors)
        pg_finished = self.postgres_ready or any("PostgreSQL" in e for e in self.connection_errors)

        if not (mssql_finished and pg_finished):
            return # Aspettiamo che finisca anche l'altro

        # Se ci sono stati errori di connessione, fermiamo tutto
        if self.connection_errors:
            self.set_led_color("#fa3e3e")
            self.label_led.setText(self.tr("Errore Connessione"))
            self.pushButton_ConnettiDB.setEnabled(True)
            QMessageBox.critical(self, self.tr("Errore di Connessione"), "\n\n".join(self.connection_errors))
            return

        # Se siamo qui, ENTRAMBE le connessioni sono andate a buon fine!
        # Lanciamo l'allineamento come prima
        try:
            is_aligned, error_message = self.verify_database_alignment()
            
            if is_aligned:
                self.set_led_color("#90ee90") # Verde chiaro
                self.label_led.setText(self.tr("Connessi e Allineati"))
            else:
                self.set_led_color("#fa3e3e") 
                self.label_led.setText(self.tr("Errore Allineamento DB!"))
                QMessageBox.critical(self, self.tr("Disallineamento Database"), 
                                     self.tr("Verifica fallita:\n\n{error_message}").format(error_message=error_message))
                # Pulizia parametri per sicurezza
                if hasattr(self, '_mssql_conn_params'): del self._mssql_conn_params
                if hasattr(self, '_postgresql_conn_params'): del self._postgresql_conn_params
                
        except Exception as e:
            self.set_led_color("#fa3e3e")
            self.label_led.setText(self.tr("Errore imprevisto"))
            QMessageBox.critical(self, self.tr("Errore Script"), self.tr("Eccezione durante la verifica:\n{error}").format(error=str(e)))
        finally:
            # Riabilitiamo il pulsante alla fine di tutto
            self.pushButton_ConnettiDB.setEnabled(True)


    # funzione per mostrare il dialogo di selezione progetto

    def show_select_dialog(self):
        # 1. Controllo di sicurezza: Abbiamo i parametri di connessione?
        if not hasattr(self, '_mssql_conn_params') or not hasattr(self, '_postgresql_conn_params'):
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Connetti prima entrambi i database (MSSQL e PostgreSQL)."))
            return

        # 2. Recupera i parametri salvati
        mssql_params = self._mssql_conn_params
        pg_params = self._postgresql_conn_params

        # 3. Passa ENTRAMBI i parametri al dialogo
        if self.select_dialog.populate_list(mssql_params, pg_params):

            # 4. Mostra il dialogo all'utente
            self.select_dialog.exec_()


    # funzione per gestire la selezione del progetto dal dialogo    

    def handle_project_selected(self):
        """Metodo chiamato quando l'utente preme OK nel dialogo di selezione"""
        
        # Recuperiamo i dati dal dialog
        result = self.select_dialog.get_selected_project()

        if result:
            self.selected_project_id, self.selected_project_name = result
            
            # Abilitiamo il tasto per eliminare
            self.pushButton_Elimina.setEnabled(True)
            
            # Feedback visivo
            QMessageBox.information(self, self.tr("Progetto Selezionato"), 
                                    self.tr("Progetto selezionato per l'eliminazione:\n{project_name}").format(project_name=self.selected_project_name))
        else:
            self.selected_project_id = None
            self.pushButton_Elimina.setEnabled(False)

    # Funzione helper per scrivere nel pannello messaggi di QGIS
   
    def log_info(self, message):
        """Scrive un messaggio nella scheda 'EliminaProgetto' del pannello Messaggi"""
        QgsMessageLog.logMessage(message, 'EliminaProgetto', Qgis.Info)        

    # Funzione per eseguire il refresh della Materialized View in background (thread separato)
    def _bg_refresh_materialized_view(self, params):
        """Metodo interno eseguito in un thread separato per il refresh della MV."""
        try:
            conn = psycopg2.connect(
                host=params[0], database=params[1], 
                user=params[2], password=params[3], port=params[4]
            )
            cur = conn.cursor()
            # CONCURRENTLY è fondamentale per non bloccare la UI di chi sta già consultando i dati
            cur.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY ifcproject.projectpostgres;')
            conn.commit()
            cur.close()
            conn.close()
            QgsMessageLog.logMessage("Materialized View aggiornata correttamente.", "ifcSQL", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Errore durante il refresh della MV: {e}", "ifcSQL", Qgis.Critical)






    # funzione principale per eliminare il progetto selezionato da entrambi i database        

    def delete_selected_project(self):
        # --- CONFIGURAZIONE ---
        BATCH_SIZE = 50000 
        
        # Helper per i log (Versione Pulita senza Timestamp)
        def log_formatted(step, msg, rows=None):
            # QGIS mette già l'orario, quindi scriviamo solo il messaggio
            row_msg = f" | Righe: {rows}" if rows is not None else ""
            self.log_info(f"{step} >> {msg}{row_msg}")
            
            # Aggiorna la GUI
            if 'progress' in locals() and progress:
                progress.setLabelText(f"{step}\n{msg}")

        # Helper per disabilitare/abilitare i vincoli (IL TRUCCO PER LA VELOCITÀ)
        def toggle_constraints(cursor, table_list, enable=True):
            state = "CHECK" if enable else "NOCHECK"
            # action = "Abilitazione" if enable else "Disabilitazione"
            
            for table in table_list:
                try:
                    # SQL Server syntax: ALTER TABLE [schema].[table] NOCHECK CONSTRAINT ALL
                    cursor.execute(f"ALTER TABLE {table} {state} CONSTRAINT ALL")
                except Exception as e:
                    # Ignoriamo errori su tabelle che magari non hanno vincoli
                    pass

        # Controllo dati
        if not self.selected_project_id or not hasattr(self, '_mssql_conn_params') or not hasattr(self, '_postgresql_conn_params'):
            QMessageBox.warning(self, self.tr("Errore"), self.tr("Dati mancanti per procedere."))
            return

        # Conferma
        confirm = QMessageBox.question(
            self, 
            self.tr("Conferma Eliminazione"),
            self.tr("ATTENZIONE: Stai per eliminare il progetto \"{project_name}\".\n\nL'operazione è irreversibile. Vuoi procedere?").format(project_name=self.selected_project_name),
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm != QMessageBox.Yes: return 

        # Progress
        progress = QProgressDialog(self.tr("Inizializzazione..."), None, 0, 100, self)
        progress.setWindowTitle(self.tr("Eliminazione IFC in corso..."))
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None) 
        progress.resize(500, 120)
        progress.show()
        QApplication.setOverrideCursor(Qt.WaitCursor)

        conn_mssql = None
        
        # Lista COMPLETA e UNICA di tutte le tabelle attributo/referenza
        # Le trattiamo tutte allo stesso modo: pulizia per GlobalEntityInstanceId
        # E se sono Ref, anche per Value.
        all_tables_list = [
            "ifcInstance.EntityAttributeListElementOfBinary",
            "ifcInstance.EntityAttributeListElementOfEntityRef", 
            "ifcInstance.EntityAttributeListElementOfListElementOfEntityRef", 
            "ifcInstance.EntityAttributeListElementOfFloat",
            "ifcInstance.EntityAttributeListElementOfInteger",
            "ifcInstance.EntityAttributeListElementOfList",
            "ifcInstance.EntityAttributeListElementOfListElementOfFloat",
            "ifcInstance.EntityAttributeListElementOfListElementOfInteger",
            "ifcInstance.EntityAttributeListElementOfString",
            "ifcInstance.EntityAttributeOfBinary",
            "ifcInstance.EntityAttributeOfBoolean",
            "ifcInstance.EntityAttributeOfEntityRef",
            "ifcInstance.EntityAttributeOfEnum",
            "ifcInstance.EntityAttributeOfFloat",
            "ifcInstance.EntityAttributeOfInteger",
            "ifcInstance.EntityAttributeOfList",
            "ifcInstance.EntityAttributeOfString",
            "ifcInstance.EntityAttributeOfVector",
            "ifcInstance.EntityVariableName"
        ]

        # Lista per sblocco vincoli (attributi + entità)
        all_tables_to_unlock = all_tables_list + ["ifcInstance.Entity"]

        try:
            # --- 1. CONNESSIONE ---
            log_formatted("STEP 1/8", self.tr("Connessione MSSQL..."))
            progress.setValue(5)
            QApplication.processEvents()

            h_ms, db_ms, u_ms, p_ms = self._mssql_conn_params
            cs_mssql = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={h_ms};DATABASE={db_ms};TrustServerCertificate=yes;"
            if u_ms and str(u_ms).strip(): cs_mssql += f"UID={u_ms};PWD={p_ms};"
            else: cs_mssql += "Trusted_Connection=yes;"

            conn_mssql = pyodbc.connect(cs_mssql, autocommit=False)
            conn_mssql.timeout = 180 # 3 minuti
            cursor_mssql = conn_mssql.cursor()

            # --- 2. IDENTIFICAZIONE ---
            log_formatted("STEP 2/8", self.tr("Analisi entità..."))
            progress.setValue(10)
            cursor_mssql.execute("CREATE TABLE #TempToDelete (GlobalEntityInstanceId INT PRIMARY KEY);")
            
            sql_fill = """
                INSERT INTO #TempToDelete (GlobalEntityInstanceId)
                SELECT GlobalEntityInstanceId
                FROM [ifcProject].[EntityInstanceIdAssignment]
                WHERE ProjectId = ?;
            """
            cursor_mssql.execute(sql_fill, (self.selected_project_id,))
            cursor_mssql.execute("SELECT COUNT(*) FROM #TempToDelete")
            count_entities = cursor_mssql.fetchone()[0]
            conn_mssql.commit()
            log_formatted("STEP 2/8", self.tr("Entità target: {count_entities}").format(count_entities=count_entities))

            # --- 3. DISABILITAZIONE VINCOLI (TURBO MODE) ---
            log_formatted("STEP 3/8", self.tr("Disabilitazione vincoli (Speed Boost)..."))
            progress.setValue(15)
            QApplication.processEvents()
            
            toggle_constraints(cursor_mssql, all_tables_to_unlock, enable=False)
            conn_mssql.commit()

            # --- 4. PULIZIA TOTALE ATTRIBUTI E REFERENZE ---
            log_formatted("STEP 4/8", self.tr("Svuotamento tabelle attributi..."))
            progress.setValue(20)
            
            total_tables = len(all_tables_list)
            
            for i, table in enumerate(all_tables_list):
                short_name = table.split('.')[-1]
                progress.setValue(20 + int((i / total_tables) * 50))
                QApplication.processEvents()
                
                # --- PASSO A: Cancellazione per GlobalEntityInstanceId (OWNER) ---
                # Questo cancella le righe che APPARTENGONO alle entità del progetto
                # (Questo era il passaggio mancante per le tabelle Ref!)
                deleted_owner = 0
                while True:
                    cursor_mssql.execute(f"""
                        DELETE TOP ({BATCH_SIZE}) T 
                        FROM {table} T 
                        INNER JOIN #TempToDelete D ON T.GlobalEntityInstanceId = D.GlobalEntityInstanceId
                    """)
                    rows = cursor_mssql.rowcount
                    deleted_owner += rows
                    conn_mssql.commit()
                    if rows < BATCH_SIZE: break
                
                # --- PASSO B: Cancellazione per Value (TARGET) - Solo per tabelle Ref ---
                # Questo cancella i riferimenti che PUNTANO alle entità del progetto
                deleted_ref = 0
                if "EntityRef" in table:
                    while True:
                        cursor_mssql.execute(f"""
                            DELETE TOP ({BATCH_SIZE}) T 
                            FROM {table} T 
                            INNER JOIN #TempToDelete D ON T.Value = D.GlobalEntityInstanceId
                        """)
                        rows = cursor_mssql.rowcount
                        deleted_ref += rows
                        conn_mssql.commit()
                        if rows < BATCH_SIZE: break
                
                total_del = deleted_owner + deleted_ref
                if total_del > 0:
                    self.log_info(f" > Pulita {short_name}: {total_del} (Own:{deleted_owner}, Ref:{deleted_ref})")

            
            # --- 5. ELIMINAZIONE ENTITY ---
            log_formatted("STEP 5/8", self.tr("Eliminazione Entità..."))
            progress.setValue(80)
            
            total_deleted_main = 0
            while True:
                cursor_mssql.execute(f"""
                    DELETE TOP ({BATCH_SIZE}) T
                    FROM [ifcInstance].[Entity] T
                    INNER JOIN #TempToDelete D ON T.GlobalEntityInstanceId = D.GlobalEntityInstanceId
                """)
                deleted = cursor_mssql.rowcount
                total_deleted_main += deleted
                conn_mssql.commit()
                if deleted < BATCH_SIZE: break
            
            log_formatted("STEP 5/8", self.tr("Tabella Entity pulita"), rows=total_deleted_main)

            # --- 6. PULIZIA PROGETTO ---
            log_formatted("STEP 6/8", self.tr("Rimozione Progetto..."))
            progress.setValue(90)

            project_deps = [
                "ifcUser.UserProjectAssignment",
                "ifcProject.EntityInstanceIdAssignment",
                "ifcProject.LastGlobalEntityInstanceId"
            ]
            for table in project_deps:
                cursor_mssql.execute(f"DELETE FROM {table} WHERE ProjectId = ?", (self.selected_project_id,))
            
            cursor_mssql.execute("DELETE FROM ifcProject.Project WHERE ProjectId = ?", (self.selected_project_id,))
            conn_mssql.commit()

            # --- 7. RIABILITAZIONE VINCOLI (SAFETY) ---
            log_formatted("STEP 7/8", self.tr("Riabilitazione vincoli..."))
            progress.setValue(95)
            
            toggle_constraints(cursor_mssql, all_tables_to_unlock, enable=True)
            conn_mssql.commit()

            cursor_mssql.close()
            conn_mssql.close()
            
            # --- 8. POSTGRESQL ---
            log_formatted("STEP 8/8", self.tr("Pulizia PostgreSQL..."))
            h_pg, db_pg, u_pg, p_pg, port_pg = self._postgresql_conn_params
            conn_pg = psycopg2.connect(host=h_pg, database=db_pg, user=u_pg, password=p_pg, port=port_pg)
            cursor_pg = conn_pg.cursor()
            try:
                cursor_pg.execute('DELETE FROM ifcgeometry.entitygeometry WHERE "ProjectNumber_MSSQL" = %s', (self.selected_project_id,))
                conn_pg.commit()
            finally:
                conn_pg.close()

            progress.setValue(100)
            QApplication.restoreOverrideCursor()
            progress.close()
            QMessageBox.information(self, self.tr("Successo"), self.tr("Eliminazione del progetto completata con successo.\n (Entità IFC rimosse: {count_entities})").format(count_entities=count_entities))
            
            self.delete_completed.emit() # Segnala al dialog principale che l'eliminazione è completata

            # Reset UI
            self.selected_project_id = None
            self.selected_project_name = None
            self.pushButton_Elimina.setEnabled(False)
            self.select_dialog.source_model.clear()

            # --- LANCIO REFRESH MV IN BACKGROUND ---
            t = threading.Thread(target=self._bg_refresh_materialized_view, args=(self._postgresql_conn_params,))
            t.daemon = True 
            t.start()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            progress.close()
            self.log_info(self.tr("[ERRORE] {e}").format(e=str(e)))
            
            # BLOCCO DI EMERGENZA: SE FALLISCE, DOBBIAMO RIABILITARE I VINCOLI!
            if conn_mssql:
                try:
                    conn_mssql.rollback() 
                    cursor_emergency = conn_mssql.cursor()
                    toggle_constraints(cursor_emergency, all_tables_to_unlock, enable=True)
                    conn_mssql.commit()
                    self.log_info(self.tr("Vincoli ripristinati dopo errore."))
                except:
                    self.log_info(self.tr("Impossibile ripristinare vincoli automaticamente."))
            
            QMessageBox.critical(self, self.tr("Errore"), self.tr("{e}").format(e=str(e)))















#     ██████  ██    ██ ███████ ██████  ██    ██      ██████ ██       █████  ███████ ███████ 
#    ██    ██ ██    ██ ██      ██   ██  ██  ██      ██      ██      ██   ██ ██      ██      
#    ██    ██ ██    ██ █████   ██████    ████       ██      ██      ███████ ███████ ███████ 
#    ██ ▄▄ ██ ██    ██ ██      ██   ██    ██        ██      ██      ██   ██      ██      ██ 
#     ██████   ██████  ███████ ██   ██    ██         ██████ ███████ ██   ██ ███████ ███████ 
#        ▀▀                                                                                 
#                                                                                           














#######################################################################
## Classe per la finestra di dialogo delle query
#######################################################################
        

class QueryDialog(Ui_Query, QDockWidget):
    def __init__(self, iface, parent=None):
        super(QueryDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # Questo è l'ID univoco che serve al codice per trovare ed eliminare i duplicati
        self.setObjectName("IfcSqlQueryDock")

        # Inizializza il LED grigio
        self.set_led_color("gray")

        # Plusanti gestione connessione DB
        self.comboBox_Connessione.currentIndexChanged.connect(self.reset_ui_on_connection_change_PostgreSQL_Query)
        self.pushButton_NuovaConnessione.clicked.connect(self.create_new_connection_PostgreSQL_Query)
        self.pushButton_ConnettiDB.clicked.connect(self.connect_selected_DB_PostgreSQL_Query)

        # Inizializza variabili per il disegno
        self.map_tool = None
        self.is_drawing = False
        self.current_area_geometry = None # Qui salveremo il WKT dell'area confermata
        # Collega il pulsante per disegnare 
        self.pushButton_DisegnaAreaSuMappa.clicked.connect(self.toggle_draw_area)

        # --- CONFIGURAZIONE MINI MAPPA ---
        # Creiamo il canvas (la mappa)
        self.mini_canvas = QgsMapCanvas()
        self.mini_canvas.setCanvasColor(Qt.white)
        self.mini_canvas.enableAntiAliasing(True)
        # Impostiamo il CRS uguale a quello del progetto corrente
        try:
            self.mini_canvas.setDestinationCrs(QgsProject.instance().crs())
        except:
            pass # Fallback se nessun progetto è aperto
        # Aggiungiamo il canvas al layout della pagina 2 (Filtro Manuale)
        self.page_2_FiltroManuale.layout().addWidget(self.mini_canvas, 2, 0)
        # Nascondiamo la mappa all'inizio
        self.mini_canvas.setVisible(False)
        # Creiamo lo strumento PAN per potersi muovere nella mini mappa
        self.tool_pan_mini = QgsMapToolPan(self.mini_canvas)
        self.mini_canvas.setMapTool(self.tool_pan_mini)


        # Inizializza la logica dei filtri contesto e IFC
        self.init_context_filters_logic()
        self.init_ifc_filters_logic()


        # Quando l'utente seleziona/deseleziona un'area (Comune/Provincia), cerca le classi IFC
        self.comboBox_SelezionaArea.checkedItemsChanged.connect(self.populate_available_ifc_classes)
        # Quando attivo/disattivo il gruppo contesto, ricalcola le classi disponibili
        self.groupBox_2_FiltroContesto.toggled.connect(self.populate_available_ifc_classes)
        # Quando l'utente clicca Applica, genera il layer
        self.button_ApplicaFiltri.clicked.connect(self.execute_filter_query)
        self.button_ResetFiltri.clicked.connect(self.reset_all_filters)


        
        


    # --- FUNZIONI DI UTILITÀ BASE --- 

    # funzione per impostare il colore del LED
    def set_led_color(self, color_name):
        palette = self.label_led.palette()
        palette.setColor(self.label_led.backgroundRole(), QColor(color_name))
        self.label_led.setAutoFillBackground(True)
        self.label_led.setPalette(palette)
        self.label_led.show()

    #resetta l'interfaccia utente quando si cambia la connessione selezionata PostgreSQL
    def reset_ui_on_connection_change_PostgreSQL_Query(self):
        """Resetta il LED e l'etichetta quando la selezione della connessione cambia."""
        self.set_led_color("gray")
        self.label_led.setText(self.tr("Seleziona e connetti"))
        
        # Rimuove i parametri salvati internamente per forzare la riconnessione
        if hasattr(self, '_postgresql_conn_params'):
            del self._postgresql_conn_params

        # --- AGGIUNTA TOOLTIP ---
        connection_name = self.comboBox_Connessione.currentText()
        if connection_name:
            s = QSettings()
            s.beginGroup(f"PostgreSQL/connections/{connection_name}")
            host = s.value("host", "N/A")
            db = s.value("database", "N/A")
            user = s.value("username", "N/A")
            port = s.value("port", "N/A")
            s.endGroup()
            
            tooltip_text = (f"<b>Connection:</b> {connection_name}<br>"
                            f"<b>Host:</b> {host}<br>"
                            f"<b>Database:</b> {db}<br>"
                            f"<b>User:</b> {user}<br>"
                            f"<b>Port:</b> {port}")
            self.comboBox_Connessione.setToolTip(tooltip_text)
        else:
            self.comboBox_Connessione.setToolTip("")

        # 2. Richiama il reset generale per pulire Mappa, Tabs e Liste
        # Usiamo silent=True per non mostrare il popup
        self.reset_all_filters(silent=True)

    #popola le combo box con le connessioni esistenti per PostgreSQL
    def populate_connection_combo_PostgreSQL_Query(self): #popola la combo box con le connessioni esistenti
        self.comboBox_Connessione.clear()  # pulisce la combo box
        settings = QSettings()
        settings.beginGroup('PostgreSQL/connections')
        connections = settings.childGroups()
        self.comboBox_Connessione.addItems(connections)

    #apre la finestra di dialogo per creare una nuova connessione per PostgreSQL
    def create_new_connection_PostgreSQL_Query(self): 
        self.iface.openDataSourceManagerPage("postgres")    

    #prendi i parametri della connessione selezionata PostgreSQL---------------------------------------------
    def connect_selected_DB_PostgreSQL_Query(self):
        selected_connection = self.comboBox_Connessione.currentText()
        if hasattr(self, '_postgresql_conn_params'): del self._postgresql_conn_params

        if not selected_connection:
            self.set_led_color("gray")
            self.label_led.setText(self.tr("Nessuna connessione selezionata"))
            return

        settings = QSettings()
        settings.beginGroup(f"PostgreSQL/connections/{selected_connection}")
        host = settings.value("host")
        database = settings.value("database")
        username = settings.value("username")
        password = settings.value("password")
        port = settings.value("port", type=int) 
        settings.endGroup()

        if not host or not database or not username or port == 0:
            self.set_led_color("#fa3e3e")
            self.label_led.setText(self.tr("Parametri mancanti"))
            return

        # UI: Connessione in corso...
        self.set_led_color("#ffd700")
        self.label_led.setText(self.tr("Connessione in corso..."))
        self.pushButton_ConnettiDB.setEnabled(False)

        # Avvio Thread
        self.pg_thread = PostgresConnectionThread(host, database, username, password, port)
        self.pg_thread.success.connect(self.on_query_connected)
        self.pg_thread.error.connect(self.on_query_error)
        self.pg_thread.start()

    def on_query_connected(self, params):
        self._postgresql_conn_params = params
        self.set_led_color("#90ee90")
        self.label_led.setText(self.tr("Connesso"))
        self.pushButton_ConnettiDB.setEnabled(True)
        
        # Popolamento dati automatico
        self.populate_territory_tables()
        if self.stackedWidget.currentIndex() == 2:
            self.populate_project_list()

    def on_query_error(self, err_msg):
        self.set_led_color("#fa3e3e")
        self.label_led.setText(self.tr("Connessione fallita"))
        self.pushButton_ConnettiDB.setEnabled(True)
        QMessageBox.warning(self, self.tr("Errore PostgreSQL"), self.tr("Impossibile raggiungere il database.\n\nDettaglio:\n{err}").format(err=err_msg))


    # Funzione chiamata alla chiusura del dock
    def closeEvent(self, event):
        # Esegue un reset completo dei filtri
        self.reset_predefined_filters(hard_reset=True)
        # 1. Resetta i filtri delle aree PAGINA 1 (Hard Reset)
        self.reset_predefined_filters(hard_reset=True)
        # 2. Resetta la logica interna della connessione (LED grigio e params)
        self.reset_ui_on_connection_change_PostgreSQL_Query()
        

        # PULIZIA STRUMENTO DISEGNO
        if self.is_drawing and self.map_tool:
            self.map_tool.reset()
            self.iface.mapCanvas().unsetMapTool(self.map_tool)
            self.is_drawing = False
            self.pushButton_DisegnaAreaSuMappa.setText(self.tr("Disegna area su mappa"))

        # RESET MAPPA
        self.reset_mini_map()

        # Chiama l'evento standard per chiudere effettivamente la finestra
        super(QueryDialog, self).closeEvent(event)
        
    # Funzione helper per ottenere una connessione al volo
    def _get_db_connection(self):
        if not hasattr(self, '_postgresql_conn_params'):
            return None
        
        host, database, username, password, port = self._postgresql_conn_params
        try:
            conn = psycopg2.connect(
                host=host,
                database=database,
                user=username,
                password=password,
                port=port
            )
            return conn
        except Exception as e:
            self.iface.messageBar().pushMessage(self.tr("Errore Connessione"), self.tr({e}).format(e=str(e)), level=3) # Level 3 = Critical
            return None







    # =========================================================================
    # GESTIONE FILTRO CONTESTO
    # =========================================================================
    def init_context_filters_logic(self):
        """Configura la ComboBox e lo StackedWidget per il Filtro Contesto."""
        
        # Pulisci e popola la ComboBox (UserData (il secondo argomento) è l'indice della pagina nello stackedWidget)
        self.comboBox_SelezionaFiltroContesto.clear()
        self.comboBox_SelezionaFiltroContesto.addItem(self.tr("Filtro Predefinito"), 0) # Page_1 (index 0)
        self.comboBox_SelezionaFiltroContesto.addItem(self.tr("Filtro Manuale"), 1)     # Page_2 (index 1)
        self.comboBox_SelezionaFiltroContesto.addItem(self.tr("Filtro Progetto"), 2)    # Page_3 (index 2)
        
        # Collega il cambio indice della combo al cambio pagina dello stacked widget
        self.comboBox_SelezionaFiltroContesto.currentIndexChanged.connect(self.change_context_page)
        # Imposta la pagina iniziale corretta
        self.change_context_page(0)

        # Pagina 1: Collega il cambio della Tabella (Tipo Area) al popolamento dei Nomi (Area)
        self.comboBox_SelezionaTipoArea.currentIndexChanged.connect(self.populate_area_names)

        # Pagina 3 - Filtro progetto
        # 1. Collega la barra di ricerca progetti
        self.lineEdit_Progetti.textChanged.connect(self.filter_project_list)
        # 2. Se cambio selezione nei progetti, aggiorna le classi IFC disponibili
        self.list_Progetti.itemChanged.connect(self.populate_available_ifc_classes)



    # Cambia la pagina visibile nello stackedWidget del filtro contesto
    def change_context_page(self, index):
        """Cambia la pagina visibile nello stackedWidget del contesto."""
        # Recupera l'indice della pagina dai dati associati all'item (più sicuro dell'indice puro)
        page_idx = self.comboBox_SelezionaFiltroContesto.itemData(index)
        
        if page_idx is not None:
            self.stackedWidget.setCurrentIndex(page_idx)
            # Se non siamo nella pagina "Filtro Predefinito" (index 0), resetta le selezioni
            if page_idx != 0:
                # Usa False per mantenere la lista delle tabelle pronta se l'utente torna indietro
                self.reset_predefined_filters(hard_reset=False)

            # SE CAMBIO PAGINA E NON SONO SULLA 1 (Manuale), RESETTA LA MAPPA
            if page_idx != 1:
                self.reset_mini_map()

            # se siamo nella pagina "Filtro Progetto", popola la lista progetti
            if page_idx == 2:
                self.populate_project_list()
            
            # Pulisce sempre la lista classi IFC quando si cambia contesto
            self.listWidget_ClasseIFC.clear()
            


 





    ##### ==============================================================
    ##### Funzioni PAGINA 1 - FILTRO PREDEFINITO 


    # 1. Popola la prima ComboBox con le tabelle dello schema 'territory'
    def populate_territory_tables(self):
        self.comboBox_SelezionaTipoArea.clear()
        self.comboBox_SelezionaArea.clear() # Pulisce anche la seconda per coerenza
        
        conn = self._get_db_connection()
        if conn is None:
            return

        try:
            cur = conn.cursor()
            # Query per ottenere i nomi delle tabelle nello schema 'territory'
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'territory' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """
            cur.execute(query)
            rows = cur.fetchall()
            
            # Aggiunge un elemento vuoto di default
            self.comboBox_SelezionaTipoArea.addItem("")
            
            for row in rows:
                self.comboBox_SelezionaTipoArea.addItem(row[0])
                
            cur.close()
            conn.close()
        except Exception as e:
            print(self.tr("Errore nel recupero tabelle: {e}").format(e=str(e)))

    # 2. Popola la seconda ComboBox con i valori 'nome' della tabella selezionata
    def populate_area_names(self):
        
        self.comboBox_SelezionaArea.clear() # Pulisce sempre la seconda combo (area) prima di riempirla
        self.listWidget_ClasseIFC.clear() # Pulisce anche le classi IFC se cambia il tipo area
        
        selected_table = self.comboBox_SelezionaTipoArea.currentText()
        # Se è selezionato l'elemento vuoto o nulla, esci
        if not selected_table:
            return

        conn = self._get_db_connection()
        if conn is None:
            return

        try:
            cur = conn.cursor()
            
            # Costruzione sicura della query. 
            query = f'SELECT DISTINCT "name" FROM territory."{selected_table}" ORDER BY "name";'
            
            cur.execute(query)
            rows = cur.fetchall()
            
            for row in rows:
                # row[0] è il valore della colonna 'name'
                if row[0] is not None:
                    self.comboBox_SelezionaArea.addItem(str(row[0]))
    
            # Opzionale: cambia il separatore che appare quando chiudi la tendina (es. "Roma, Milano")
            self.comboBox_SelezionaArea.setSeparator(", ")
            
            cur.close()
            conn.close()
        except psycopg2.Error as e:
            # Questo gestisce il caso in cui la colonna "name" non esista
            self.iface.messageBar().pushMessage(self.tr("Errore SQL"), self.tr("La tabella '{table}' non ha una colonna 'name' o errore query.").format(table=selected_table), level=2)
        except Exception as e:
            print(self.tr("Errore generico popolamento aree: {e}").format(e=str(e)))

    # Funzione dedicata per resettare i widget della pagina "Filtro Predefinito"
    def reset_predefined_filters(self, hard_reset=False):
        """
        hard_reset=True: Rimuove tutte le voci (usato quando cambia DB o si chiude).
        hard_reset=False: Resetta solo la selezione (usato quando si cambia pagina).
        """
        # Resetta sempre la selezione e svuota la seconda combo (Aree/Comuni)
        self.comboBox_SelezionaTipoArea.setCurrentIndex(-1) 
        self.comboBox_SelezionaArea.clear()
        self.listWidget_ClasseIFC.clear()
        
        # Se è un reset "forte" (cambio DB o chiusura), svuota anche la lista delle tabelle
        if hard_reset:
            self.comboBox_SelezionaTipoArea.clear()





    ##### ==============================================================
    ##### Funzioni PAGINA 2 - FILTRO MANUALE

    def toggle_draw_area(self):
        """Attiva o Disattiva la modalità disegno"""
        
        # --- CONTROLLO PRELIMINARE CONNESSIONE ---
        # Verifichiamo la connessione SOLO se stiamo provando ad ATTIVARE il disegno.
        # Se stiamo disattivando (is_drawing = True), lasciamo proseguire per chiudere correttamente.
        if not self.is_drawing:
            if not hasattr(self, '_postgresql_conn_params'):
                QMessageBox.warning(
                    self, 
                    self.tr("Database non connesso"), 
                    self.tr("Attenzione: Non sei connesso al database PostgreSQL.\n\nÈ necessario connettersi prima di selezionare un'area, altrimenti non sarà possibile recuperare le classi IFC contenute nella selezione."
                    )
                )
                return # Interrompe la funzione: il cursore non cambierà e il disegno non partirà.

        canvas = self.iface.mapCanvas()

        if not self.is_drawing:
            # --- INIZIO DISEGNO ---
            self.is_drawing = True
            
            # 1. Crea lo strumento se non esiste
            if not self.map_tool:
                self.map_tool = AreaSelectorTool(canvas)
            
            # 2. Attiva lo strumento sulla mappa
            canvas.setMapTool(self.map_tool)
            
            # 3. Cambia il testo del pulsante
            self.pushButton_DisegnaAreaSuMappa.setText(self.tr("Fine disegno"))
            # Cambia lo stile: Sfondo Rosso, Testo Bianco, Grassetto
            self.pushButton_DisegnaAreaSuMappa.setStyleSheet("background-color: red; color: white; font-weight: bold;")
            

        else:
            # --- FINE DISEGNO (Click dell'utente su "Fine disegno") ---
            self.finish_drawing_sequence()


    # Funzione per gestire la chiusura del disegno, la conferma e la pulizia
    def finish_drawing_sequence(self):
        """Gestisce la chiusura, la conferma e la pulizia"""
        
        # 1. Chiede conferma
        reply = QMessageBox.question(
            self, 
            self.tr("Conferma Area"), 
            self.tr("Vuoi confermare l'area disegnata e utilizzarla come filtro?"),
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.Yes
        )

        # 2. Recupera la geometria PRIMA di pulire
        if self.map_tool:
            temp_geom = self.map_tool.get_geometry()
        else:
            temp_geom = None

        # 3. Pulisce la mappa (Reset visuale)
        if self.map_tool:
            self.map_tool.reset()           # Rimuove rosso e pallini
            self.iface.mapCanvas().unsetMapTool(self.map_tool) # Rimuove il cursore a croce

        # 4. Gestione Risposta
        if reply == QMessageBox.Yes:
            # Caso A: L'utente dice SI
            if temp_geom and not temp_geom.isEmpty() and temp_geom.isGeosValid():
                self.current_area_geometry = temp_geom
                
                # CHIAMATA ALLA NUOVA FUNZIONE
                self.show_geometry_on_mini_map(self.current_area_geometry)

                # --- AGGIORNA LA LISTA CLASSI IFC SUBITO ---
                self.populate_available_ifc_classes()

            # Caso B: L'utente dice SI, ma la geometria è invalida
            else:
                QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Area non valida o non chiusa (servono almeno 3 punti)."))
                self.reset_mini_map() # Resetta se non valido

                # --- Aggiorna la lista IFC (La svuota perché non c'è geometria) ---
                self.populate_available_ifc_classes()

        # Caso C: L'utente dice NO (Annulla)
        else:
            self.reset_mini_map() # Resetta se annullato

            # --- Aggiorna la lista (La svuota perché non c'è geometria) ---
            self.populate_available_ifc_classes()


        # 5. Ripristina stato UI
        self.is_drawing = False
        self.pushButton_DisegnaAreaSuMappa.setText(self.tr("Disegna area su mappa"))
        # Rimuovi lo stile (impostando una stringa vuota torna allo stile di default di QGIS)
        self.pushButton_DisegnaAreaSuMappa.setStyleSheet("")
        self.map_tool = None # Opzionale: distrugge il tool per ricrearlo pulito la prossima volta


    # Funzione per mostrare la geometria disegnata nella mini mappa
    def show_geometry_on_mini_map(self, geometry):
        """
        Visualizza la geometria disegnata nella mini mappa clonando i layer di sfondo.
        """
        if not geometry:
            return

        # 1. Rendi visibile la mappa e nascondi l'etichetta
        self.mini_canvas.setVisible(True)
        self.label_AreaDisegnata.setVisible(False)

        # 2. SINCRONIZZAZIONE CRS (FONDAMENTALE)
        # Recuperiamo le impostazioni attuali della mappa principale
        main_settings = self.iface.mapCanvas().mapSettings()
        current_crs = main_settings.destinationCrs()
        
        # Impostiamo la mini mappa con LO STESSO CRS della mappa principale
        self.mini_canvas.setDestinationCrs(current_crs)
        
        # 3. Creazione Layer Temporaneo
        # Usiamo il CRS corrente per creare il layer
        # [IMPORTANTE] Salviamo in self.temp_mini_layer per evitare che venga distrutto dal garbage collector
        self.temp_mini_layer = QgsVectorLayer(f"Polygon?crs={current_crs.authid()}", "Area Filtro", "memory")
        
        # Aggiungi la feature
        prov = self.temp_mini_layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(geometry)
        prov.addFeatures([feat])
        self.temp_mini_layer.updateExtents()

        # Imposta uno stile semplice (Rosso semitrasparente)
        symbol = self.temp_mini_layer.renderer().symbol()
        symbol.setColor(QColor(255, 0, 0, 100)) # Rosso trasparente
        symbol.symbolLayer(0).setStrokeColor(QColor(255, 0, 0))
        symbol.symbolLayer(0).setStrokeWidth(0.5)
        
        # 4. Gestione Sfondo: Recupera i layer attuali dalla mappa principale
        # Nota: in setLayers, l'indice 0 è il layer più in ALTO (Topmost)
        main_canvas_layers = self.iface.mapCanvas().layers()
        
        # Creiamo la lista finale: Il nostro poligono [0] + Sfondi [1, 2, ...]
        layers_to_show = [self.temp_mini_layer] + main_canvas_layers
        
        self.mini_canvas.setLayers(layers_to_show)
        
        # 5. Zoom sull'estensione del poligono
        # Poiché ora MiniMappa e Geometria hanno lo STESSO CRS, il boundingBox è corretto
        extent = geometry.boundingBox()
        extent.scale(1.3) # Zoom out del 30% per vedere il contesto
        self.mini_canvas.setExtent(extent)
        
        self.mini_canvas.refresh()



    # Funzione per resettare la mini mappa e nascondere il widget
    def reset_mini_map(self):
        """Resetta la mini mappa e nasconde il widget."""

        # [SICUREZZA] Controlla se la mini_canvas esiste prima di usarla
        if not hasattr(self, 'mini_canvas') or self.mini_canvas is None:
            return
       
        # Ferma rendering
        self.mini_canvas.stopRendering()
        # Rimuove i layer (importante per non tenere locati i layer di progetto)
        self.mini_canvas.setLayers([]) 
        # Nasconde il widget
        self.mini_canvas.setVisible(False)

        # Pulizia della variabile del layer temporaneo
        if hasattr(self, 'temp_mini_layer'):
            self.temp_mini_layer = None

        # Mostra l'etichetta di placeholder
        if hasattr(self, 'label_AreaDisegnata'):
            self.label_AreaDisegnata.setVisible(True)
            self.label_AreaDisegnata.setText(self.tr("Nessuna area disegnata."))
        
        self.current_area_geometry = None






    # =========================================================================
    # Funzioni PAGINA 3 - FILTRO PROGETTO
    
    def populate_project_list(self):
        """Popola la lista dei progetti prendendo i nomi unici da entitygeometry."""
        self.list_Progetti.clear()
        
        conn = self._get_db_connection()
        if conn is None:
            return

        try:
            cur = conn.cursor()
            # Interroghiamo la MV
            query = 'SELECT "ProjectName" FROM ifcproject.projectpostgres ORDER BY "ProjectName";'

            cur.execute(query)
            rows = cur.fetchall()
            
            if not rows:
                self.list_Progetti.addItem(self.tr("Nessun progetto trovato."))
            
            for row in rows:
                p_name = row[0]
                if p_name: # Controllo che non sia None
                    item = QListWidgetItem(str(p_name))
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.list_Progetti.addItem(item)
            
            cur.close()
            conn.close()
            
        except Exception as e:
            self.iface.messageBar().pushMessage(self.tr("Errore DB"), self.tr("Impossibile recuperare progetti: {e}").format(e=e), level=2)


    def filter_project_list(self, text):
        """Filtra la lista progetti in base al testo (barra di ricerca)."""
        for i in range(self.list_Progetti.count()):
            item = self.list_Progetti.item(i)
            # Case insensitive search
            if text.lower() in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def reset_project_filter(self):
        """Resetta la lista dei progetti: toglie le spunte e pulisce la ricerca."""
        # 1. Pulisce la barra di ricerca
        self.lineEdit_Progetti.clear()
        
        # 2. Deseleziona tutti gli elementi della lista
        for i in range(self.list_Progetti.count()):
            item = self.list_Progetti.item(i)
            item.setCheckState(Qt.Unchecked)
            item.setHidden(False) # Si assicura che siano tutti visibili











    # =========================================================================
    # GESTIONE FILTRO IFC
    # =========================================================================
    def init_ifc_filters_logic(self):
        """Configura la ComboBox e lo StackedWidget per il Filtro IFC."""
        
        self.comboBox_SelezionaFIltroIFC.clear()
        self.comboBox_SelezionaFIltroIFC.addItem(self.tr("Filtro Classe IFC"), 0) # Page_1 (index 0)
        
        # Collega il segnale
        self.comboBox_SelezionaFIltroIFC.currentIndexChanged.connect(self.change_ifc_page)
        
        # Imposta pagina iniziale
        self.change_ifc_page(0)

        # Collega la barra di ricerca alla funzione di filtro
        self.lineEdit_ClasseIFC.textChanged.connect(self.filter_ifc_list)

    def change_ifc_page(self, index):
        """Cambia la pagina visibile nello stackedWidget IFC."""
        page_idx = self.comboBox_SelezionaFIltroIFC.itemData(index)
        if page_idx is not None:
            self.stackedWidget_2.setCurrentIndex(page_idx)

    
    # Funzione per filtrare la lista delle classi IFC
    def filter_ifc_list(self, text):
        """
        Filtra la lista delle classi IFC in base al testo inserito.
        """
        # Itera su tutti gli elementi della lista
        for i in range(self.listWidget_ClasseIFC.count()):
            item = self.listWidget_ClasseIFC.item(i)
            
            # Se il testo digitato è contenuto nel testo dell'item (case-insensitive)
            if text.lower() in item.text().lower():
                item.setHidden(False) # Mostra
            else:
                item.setHidden(True)  # Nascondi
            




    # =========================================================================
    # Funzioni pagina 1 - Filtro classe IFC

    def populate_available_ifc_classes(self):
        """
        Popola la lista delle classi IFC.
        - Se il Filtro Contesto è ATTIVO: Mostra solo classi nell'area selezionata.
        - Se il Filtro Contesto è SPENTO: Mostra TUTTE le classi del database.
        """

        # Pulisce la lista classi
        self.listWidget_ClasseIFC.clear()

        # Se non c'è connessione, esci
        if not hasattr(self, '_postgresql_conn_params'):
            return

        
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            rows = []

            # --- CASO 1: CONTESTO ATTIVO ---
            if self.groupBox_2_FiltroContesto.isChecked():
                
                # Capiamo quale sottomodulo è attivo (0=Aree, 1=Manuale, 2=Progetti)
                current_page_idx = self.stackedWidget.currentIndex()

                # A. MODULO PREDEFINITO (Aree Geografiche)
                if current_page_idx == 0:
                    selected_table = self.comboBox_SelezionaTipoArea.currentText()
                    selected_areas = self.comboBox_SelezionaArea.checkedItems()

                    if selected_table and selected_areas:
                        QApplication.setOverrideCursor(Qt.WaitCursor) 
                        
                        areas_formatted = ", ".join([f"'{a.replace('\'', '\'\'')}'" for a in selected_areas])
                        query = f"""
                            SELECT DISTINCT g."IfcClass"
                            FROM "ifcgeometry"."entitygeometry" g
                            JOIN "territory"."{selected_table}" t 
                            ON t."name" IN ({areas_formatted})
                            WHERE ST_Within(g."Geometry", t.geom)
                            ORDER BY g."IfcClass";
                        """
                        cur.execute(query)
                        rows = cur.fetchall()

                # B. MODULO MANUALE ---
                elif current_page_idx == 1:
                    # Verifica che esista una geometria disegnata
                    if self.current_area_geometry:
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        
                        # Ottieni il WKT della geometria disegnata
                        wkt_area = self.current_area_geometry.asWkt()
                        
                        # Ottieni SRID del progetto corrente per assicurarci che PostGIS capisca le coordinate
                        srid = self.iface.mapCanvas().mapSettings().destinationCrs().postgisSrid()
                        
                        # Query Spaziale: ST_Intersects, oggetti che intersecano l'area (posso cambiare con ST_Within solo gli oggetti dentro l'area)
                        # Nota: Usiamo ST_GeomFromText per convertire il WKT disegnato in geometria DB
                        query = f"""
                            SELECT DISTINCT g."IfcClass"
                            FROM "ifcgeometry"."entitygeometry" g
                            WHERE ST_Intersects(g."Geometry", ST_GeomFromText('{wkt_area}', {srid}))
                            ORDER BY g."IfcClass";
                        """
                        cur.execute(query)
                        rows = cur.fetchall()

                # C. MODULO PROGETTO
                elif current_page_idx == 2:
                    # Recupera i progetti che hanno la spunta
                    selected_projects = []
                    for i in range(self.list_Progetti.count()):
                        item = self.list_Progetti.item(i)
                        if item.checkState() == Qt.Checked:
                            selected_projects.append(item.text())
                    
                    if selected_projects:
                        QApplication.setOverrideCursor(Qt.WaitCursor) # Mettiamo la clessidra anche qui
                        
                        projects_formatted = ", ".join([f"'{p.replace('\'', '\'\'')}'" for p in selected_projects])
                        query = f"""
                            SELECT DISTINCT "IfcClass"
                            FROM "ifcgeometry"."entitygeometry"
                            WHERE "ProjectName" IN ({projects_formatted})
                            ORDER BY "IfcClass";
                        """
                        cur.execute(query)
                        rows = cur.fetchall()

            # --- CASO 2: CONTESTO DISATTIVATO (Tutto il DB) ---
            else:
                QApplication.setOverrideCursor(Qt.WaitCursor) 
                query = """
                    SELECT DISTINCT "IfcClass"
                    FROM "ifcgeometry"."entitygeometry"
                    ORDER BY "IfcClass";
                """
                cur.execute(query)
                rows = cur.fetchall()
        
            # Popola il Widget
            if not rows:
                self.listWidget_ClasseIFC.addItem(self.tr("Nessuna classe trovata (o selezione vuota)."))
            else:
                for row in rows:
                    item = QListWidgetItem(row[0])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.listWidget_ClasseIFC.addItem(item)

            cur.close()

        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore Database"), self.tr("Errore nel recupero classi IFC:\n{e}").format(e=e))
        finally:
            if conn: conn.close()
            QApplication.restoreOverrideCursor() # Mantenuto dall'originale






    # =========================================================================
    # GESTIONE PULSANTI GENERALI: APPLICA E RESET
    # =========================================================================

    # APPLICA FILTRI E CREA LAYER (Al momento funziona solo filtro predefinito + filtro IFC)
    def execute_filter_query(self):
        """
        Genera un layer temporaneo costruendo la query SQL dinamicamente
        in base ai gruppi attivati (Contesto / IFC).
        """
        # 0. Verifica Connessione
        if not hasattr(self, '_postgresql_conn_params'):
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Database non connesso."))
            return

        # 1. Verifica stati dei gruppi (Checkbox)
        use_context = self.groupBox_2_FiltroContesto.isChecked()
        use_ifc = self.groupBox_3_FiltroIFC.isChecked()

        # Se entrambi sono spenti, avvisa l'utente
        if not use_context and not use_ifc:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Seleziona almeno un filtro (Contesto o IFC) o attivali entrambi."))
            return
        
        # --- PREPARAZIONE DATI IFC ---
        selected_classes = []
        if use_ifc:
            for index in range(self.listWidget_ClasseIFC.count()):
                item = self.listWidget_ClasseIFC.item(index)
                if item.checkState() == Qt.Checked:
                    selected_classes.append(item.text())
            
            if not selected_classes:
                QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Filtro IFC attivo: Seleziona almeno una classe dalla lista."))
                return

        # --- CONTROLLO AVVISO DATABASE COMPLETO ---
        # Condizione: Filtro IFC attivo MA Filtro Contesto spento
        if use_ifc and not use_context:
            # Formatta la lista delle classi per il messaggio (es. "IfcWall, IfcWindow")
            classi_str = ", ".join(selected_classes)
            
            # Se la stringa è troppo lunga (es. troppe classi), la tronchiamo per leggibilità
            if len(classi_str) > 100:
                classi_str = classi_str[:100] + "..."

            reply = QMessageBox.question(
                self, 
                self.tr("Conferma Query Estesa"), 
                self.tr("Stai filtrando {classi_str} dell'intero database.\n\nIl filtro potrebbe richiedere tempo in base all'estensione del database.\nVuoi procedere?").format(classi_str=classi_str),
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return # Interrompe l'esecuzione

        # 4. COSTRUZIONE DINAMICA SQL
        # Inizializziamo le parti della query come nell'originale
        select_part = ['g.*'] 
        from_part = ['"ifcgeometry"."entitygeometry" g']
        where_conditions = [] 

        # --- LOGICA CONTESTO ---
        if use_context:
            # Dobbiamo sapere QUALE filtro contesto usare
            current_page_idx = self.stackedWidget.currentIndex()

            # CASO A: Filtro Predefinito (Aree Geografiche)
            if current_page_idx == 0:
                selected_table = self.comboBox_SelezionaTipoArea.currentText()
                selected_areas = self.comboBox_SelezionaArea.checkedItems()
                
                if not selected_table or not selected_areas:
                    QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Filtro Contesto attivo: Seleziona un'area geografica."))
                    return

                # Aggiungiamo il name del territorio alla select 
                select_part.append('t."name" as territory_name')
                # Aggiungiamo la tabella territorio 
                from_part.append(f'JOIN "territory"."{selected_table}" t ON ST_Within(g."Geometry", t.geom)')
                
                # Filtro WHERE sui nomi delle aree
                areas_sql = ", ".join([f"'{a.replace('\'', '\'\'')}'" for a in selected_areas])
                where_conditions.append(f't."name" IN ({areas_sql})')

            # CASO B: Filtro Manuale ---
            elif current_page_idx == 1:
                if not self.current_area_geometry:
                    QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Filtro Manuale attivo: Disegna e conferma un'area sulla mappa."))
                    return
                
                # Ottieni WKT e SRID
                wkt_area = self.current_area_geometry.asWkt()
                srid = self.iface.mapCanvas().mapSettings().destinationCrs().postgisSrid()
                
                # Aggiunge la condizione spaziale
                # ST_Intersects prende tutto ciò che tocca l'area. 
                # Se vuoi solo ciò che è strettamente dentro, usa ST_Within.
                where_conditions.append(f"ST_Intersects(g.\"Geometry\", ST_GeomFromText('{wkt_area}', {srid}))")

            # CASO C: Filtro Progetto 
            elif current_page_idx == 2:
                # Recuperiamo i progetti selezionati
                selected_projects = []
                for i in range(self.list_Progetti.count()):
                    item = self.list_Progetti.item(i)
                    # Controlliamo che sia spuntato E visibile
                    if item.checkState() == Qt.Checked and not item.isHidden():
                        selected_projects.append(item.text())
                
                if not selected_projects:
                    QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Filtro Progetto attivo: Seleziona almeno un progetto."))
                    return
                
                # Qui NON facciamo join con territory, ma filtriamo su ProjectName
                projects_sql = ", ".join([f"'{p.replace('\'', '\'\'')}'" for p in selected_projects])
                where_conditions.append(f'g."ProjectName" IN ({projects_sql})')

        # --- LOGICA IFC ---
        if use_ifc:
            # Nota: selected_classes è già stato popolato sopra per il controllo warning
            classes_sql = ", ".join([f"'{c}'" for c in selected_classes])
            where_conditions.append(f'g."IfcClass" IN ({classes_sql})')

        # --- SICUREZZA ---
        if not where_conditions:
            QMessageBox.warning(self, self.tr("Operazione Annullata"), self.tr("Nessun filtro specifico rilevato."))
            return    

        # --- ASSEMBLAGGIO QUERY ---
        sql_select = ", ".join(select_part)
        sql_from = " ".join(from_part)    
        sql_where = "WHERE " + " AND ".join(where_conditions)
        final_sql = f"SELECT {sql_select} FROM {sql_from} {sql_where}"

        print(self.tr("Query Generata: {final_sql}").format(final_sql=final_sql))

        # 5. Configurazione Layer QGIS (Invariata)
        host, database, username, password, port = self._postgresql_conn_params
        
        uri = QgsDataSourceUri()
        uri.setConnection(host, str(port), database, username, password)
        uri.setDataSource("", f"({final_sql})", "Geometry", "", "GlobalId_MSSQL")
        
        # --- Generazione Nome Layer Dinamico ---
        layer_parts = []
        
        # 1. Parte CONTESTO (Aree o Progetti)
        if use_context: 
            # CASO A: Aree Geografiche
            if self.stackedWidget.currentIndex() == 0:
                # 'selected_areas' è stato popolato nel blocco SQL sopra
                if len(selected_areas) <= 3:
                    aree_unite = ", ".join(selected_areas)
                    layer_parts.append(self.tr("Aree ({aree_unite})").format(aree_unite=aree_unite))
                else:
                    layer_parts.append(self.tr("Aree Geografiche"))

            # CASO B: Manuale ---
            elif self.stackedWidget.currentIndex() == 1:
                layer_parts.append(self.tr("Area Manuale"))
            
            # CASO C: Progetti
            elif self.stackedWidget.currentIndex() == 2:
                # 'selected_projects' è stato popolato nel blocco SQL sopra
                if len(selected_projects) <= 3:
                    layer_parts.append(self.tr("Progetti ({projects})").format(projects=", ".join(selected_projects)))
                else:
                    layer_parts.append(self.tr("Progetti"))

        # 2. Parte IFC (Classi)
        if use_ifc: 
            # 'selected_classes' è stato popolato all'inizio della funzione
            if len(selected_classes) <= 3:
                layer_parts.append(self.tr("Classi ({classes})").format(classes=", ".join(selected_classes)))
            else:
                layer_parts.append(self.tr("Classi IFC"))

        # Unisce le parti con un " + "    
        layer_name = self.tr("Filtro: ") + " + ".join(layer_parts)

        # 6. Caricamento Layer (Invariato)
        vlayer = QgsVectorLayer(uri.uri(False), layer_name, "postgres")
        
        if vlayer.isValid():
            QgsProject.instance().addMapLayer(vlayer)
            self.iface.messageBar().pushMessage(self.tr("Successo"), self.tr("Layer '{layer_name}' caricato.").format(layer_name=layer_name), level=Qgis.Success)
        else:
            QMessageBox.critical(self, self.tr("Errore Caricamento"), self.tr("Il layer non è valido."))


    # RESET COMPLETO DEI FILTRI
    def reset_all_filters(self, silent=False):
        """Reset completo invocato dal bottone Reset"""
        
        # 1. Resetta le selezioni interne (Aree, Progetti, Classi)
        self.reset_predefined_filters(hard_reset=False)
        self.reset_project_filter()

        # RESET MAPPA
        self.reset_mini_map()
        if self.is_drawing and self.map_tool:
            self.map_tool.reset()
            self.iface.mapCanvas().unsetMapTool(self.map_tool)
            self.is_drawing = False
            self.pushButton_DisegnaAreaSuMappa.setText(self.tr("Disegna area su mappa"))
            self.pushButton_DisegnaAreaSuMappa.setStyleSheet("")
        
        # Resetta liste e ricerche IFC
        self.listWidget_ClasseIFC.clear()
        self.lineEdit_ClasseIFC.clear() 

        # 2. Ripristina lo stato dei Gruppi (Li riattiva entrambi)
        self.groupBox_2_FiltroContesto.setChecked(True)
        self.groupBox_3_FiltroIFC.setChecked(True)

        # 3. Ripristina la posizione della Tab (Torna a "Filtro Predefinito")
        self.comboBox_SelezionaFiltroContesto.setCurrentIndex(0)

        # 4. Ripristina la posizione della Tab IFC (Torna a "Filtro Classe IFC")
        self.comboBox_SelezionaFIltroIFC.setCurrentIndex(0)

        # Mostra il messaggio SOLO se non è silenzioso
        if not silent:
            QMessageBox.information(self, self.tr("Reset"), self.tr("Tutti i filtri sono stati reimpostati allo stato iniziale."))

    
    










# =========================================================================
# MAP TOOL PER DISEGNARE L'AREA MANUALMENTE
# ========================================================================    
        
class AreaSelectorTool(QgsMapToolEmitPoint):
    def __init__(self, canvas):
        self.canvas = canvas
        super().__init__(self.canvas)
        
        # Geometria temporanea (Poligono rosso)
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setColor(QColor(255, 0, 0, 255))  # Contorno Rosso deciso
        self.rubberBand.setFillColor(QColor(255, 0, 0, 40))  # Interno Rosso sfumato (trasparente)
        self.rubberBand.setWidth(2)
        
        # Lista per i punti (pallini rossi)
        self.markers = []
        self.points = []

        # Cursore speciale a croce
        self.setCursor(Qt.CrossCursor)

    def canvasReleaseEvent(self, event):
        # Ottieni le coordinate del click trasformate
        point = self.toMapCoordinates(event.pos())
        
        # 1. Aggiungi il punto alla logica
        self.points.append(point)
        
        # 2. Aggiungi il "Pallino Rosso" (Vertex Marker)
        marker = QgsVertexMarker(self.canvas)
        marker.setCenter(point)
        marker.setColor(QColor(255, 0, 0))
        marker.setIconSize(5)
        marker.setIconType(QgsVertexMarker.ICON_CIRCLE) # O ICON_BOX, ICON_X, ecc.
        marker.setPenWidth(3)
        self.markers.append(marker)
        
        # 3. Aggiorna la geometria (RubberBand)
        # La rubberband gestisce da sola la connessione dei punti
        self.rubberBand.addPoint(point, True) # True = aggiorna la visualizzazione
        self.rubberBand.show()

    def reset(self):
        """Pulisce tutto dalla mappa"""
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
        for marker in self.markers:
            self.canvas.scene().removeItem(marker)
        self.markers.clear()
        self.points.clear()

    def get_geometry(self):
        """Restituisce la geometria finale come QgsGeometry"""
        if len(self.points) < 3:
            return None
        return self.rubberBand.asGeometry()









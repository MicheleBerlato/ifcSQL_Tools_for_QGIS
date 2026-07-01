# Importa librerie di QGIS
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox, QDialog, QAbstractItemView, QMainWindow, QFileDialog, QProgressDialog, QApplication, QDockWidget, QListWidgetItem, QCheckBox, QTreeWidgetItem, QVBoxLayout, QDialogButtonBox, QTextEdit, QHeaderView
from qgis.PyQt.QtGui import QIcon, QColor, QStandardItemModel, QStandardItem, QFont
from qgis.PyQt.QtCore import QSettings, Qt, QSortFilterProxyModel, pyqtSignal, QCoreApplication, QTranslator, QThread, QTimer
from qgis.core import Qgis, QgsMessageLog, QgsVectorLayer, QgsDataSourceUri, QgsProject, QgsWkbTypes, QgsFeature, QgsRectangle, QgsFeatureRequest, NULL, QgsGeometry
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand, QgsVertexMarker, QgsMapCanvas, QgsMapToolPan, QgsMapToolExtent, QgsMapTool
from qgis._3d import Qgs3DMapCanvas, Qgs3DMapSettings



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
import concurrent.futures



# Definisce flag per nascondere le finestre di console su Windows
if os.name == 'nt':
    HIDE_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW
else:
    HIDE_WINDOW_FLAGS = 0

# Importa librerie esterne 
try:
    import ifcopenshell
    import ifcopenshell.geom
    IFCOPENSHELL_PRESENTE = True
except ImportError:
    IFCOPENSHELL_PRESENTE = False # La libreria non è installata


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
from .UIs.DockFilter import Ui_Filter
from .UIs.SelezionaProgettoDaEliminare import Ui_SelezionaProgetto
from .UIs.DockQueryProperties import Ui_QueryProperties




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
        self.properties_dialog = None

        # Inizializza le azioni del menu e della toolbar
        self.action1 = None
        self.action2 = None
        self.action3 = None
        self.action4 = None
        self.action_properties = None
        self.action5 = None
        

        # Variabile per tracciare il canvas 3D
        self.canvas_3d = None

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
        self.action4 = QAction(QIcon(os.path.join(plugin_directory, 'icons', 'icon_filter.png')), self.tr("IFC filter"), self.iface.mainWindow())
        self.action4.setCheckable(True) 
        self.menu.addAction(self.action4)
        self.action4.triggered.connect(self.run_query)

        # Pulsante 6
        self.action_properties = QAction(QIcon(os.path.join(plugin_directory, 'icons', 'icon_query2.png')), self.tr("Interroga elemento IFC"), self.iface.mainWindow())
        self.menu.addAction(self.action_properties)
        self.action_properties.triggered.connect(self.run_properties)

        # Pulsante 5
        self.action5 = QAction(QIcon(os.path.join(plugin_directory, 'icons', 'icon_3dmap.png')), self.tr("3D Map View"), self.iface.mainWindow())
        self.menu.addAction(self.action5)
        self.action5.triggered.connect(self.run_3dmap) 

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
        self.toolbar.addAction(self.action_properties)
        self.toolbar.addAction(self.action5)

    # Rimuovi l'interfaccia grafica del plugin    

    def unload(self):
        # 1. Rimuovi il Dock Widget se esiste
        if self.query_dialog:
            self.iface.removeDockWidget(self.query_dialog)
            self.query_dialog.deleteLater()
            self.query_dialog = None
        
        # 2. Rimuovi il Dock delle proprietà se esiste
        if self.properties_dialog:
            self.iface.removeDockWidget(self.properties_dialog)
            self.properties_dialog.deleteLater()
            self.properties_dialog = None
        
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
            self.query_dialog.reset_ui_on_connection_change_MSSQL_Query()

    def run_query(self, checked):
        # --- 1. CREAZIONE E CONFIGURAZIONE INIZIALE ---
        if not self.query_dialog:
            self.query_dialog = QueryDialog(self.iface, parent=self.iface.mainWindow())
            self.query_dialog.setObjectName("IfcSqlQueryDock") 
            
            # Aggiungiamo il widget (inizialmente nascosto o visibile a seconda di checked)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.query_dialog)
            
            # Collega eventi
            self.query_dialog.visibilityChanged.connect(self.action4.setChecked)
            self.query_dialog.populate_connection_combo_PostgreSQL_Query()
            self.query_dialog.populate_connection_combo_MSSQL_Query()

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

    # --- 3. FUNZIONE HELPER PER GESTIRE L'AGGIANCIO ---
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
    

    def force_tabify_properties_dock(self):
        """
        Cerca il pannello Query o un altro pannello a destra e forza 
        la creazione delle schede (Tabs) per il pannello proprietà.
        """
        mainWindow = self.iface.mainWindow()
        
        # Se il pannello è già inserito in una scheda, non fare nulla
        if mainWindow.tabifiedDockWidgets(self.properties_dialog):
            return

        target_dock = None
        
        # Priorità 1: Se il pannello Query (Filtro IFC) è aperto a destra, ci agganciamo a lui
        if self.query_dialog and self.query_dialog.isVisible() and not self.query_dialog.isFloating():
            if mainWindow.dockWidgetArea(self.query_dialog) == Qt.RightDockWidgetArea:
                target_dock = self.query_dialog
                
        # Priorità 2: Se il pannello query è chiuso, cerchiamo i pannelli standard di QGIS
        if not target_dock:
            priority_docks = ["IdentifyResults", "LayerOrder", "StatisticsDockWidget", "AdvancedDigitizingPanel"]
            for name in priority_docks:
                dock = mainWindow.findChild(QDockWidget, name)
                if (dock and dock.isVisible() and not dock.isFloating() and 
                    mainWindow.dockWidgetArea(dock) == Qt.RightDockWidgetArea):
                    target_dock = dock
                    break
                    
        # Eseguiamo l'aggancio a schede
        if target_dock:
            mainWindow.tabifyDockWidget(target_dock, self.properties_dialog)






    #-----------------------------------------------
    # Gestione mappa 3D

    def run_3dmap(self):
        """Fase 1: Attiva lo strumento per disegnare il ritaglio sulla mappa 2D"""
        
        # --- BLOCCO: una sola vista 3D del plugin alla volta ---
        if getattr(self, 'canvas_3d', None) is not None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "3D Map View",
                self.tr("C'è già una mappa 3D aperta creata con questo strumento.\n\n"
                        "Chiudi prima la vista \"IFC 3D View\" esistente per "
                        "ripristinare i filtri, poi potrai crearne una nuova.")
            )
            return

        # 1. Creiamo la spunta (CheckBox)
        self.cb_nascondi_space = QCheckBox(self.tr("Nascondi i volumi degli IfcSpace."))
        self.cb_nascondi_space.setChecked(True) # Selezionato di default

        # 2. Ripristiniamo la tua finestra originale e inseriamo la spunta
        msgBox = QMessageBox(self.iface.mainWindow())
        msgBox.setWindowTitle("3D Map View")
        msgBox.setText(self.tr("-- STRUMENTO DI DISEGNO --\nDisegna un rettangolo sulla mappa per ritagliare l'area da vedere in 3D.\n"
        "Clicca e trascina per disegnare, poi rilascia il mouse per confermare.\n\n-- FILTRI IFC (chiudi la mappa 3D per ripristinare i filtri) --"))
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msgBox.setCheckBox(self.cb_nascondi_space) # Aggiunge la spunta in basso

        # Mostra l'avviso e controlla la risposta
        risposta = msgBox.exec_()

        # Controlla cosa ha cliccato l'utente
        if risposta == QMessageBox.Cancel:
            # L'utente ha annullato, usciamo dalla funzione senza fare nulla
            return

        # Salviamo la scelta dell'utente per la Fase 2
        self.nascondi_ifcspace = self.cb_nascondi_space.isChecked()

        # Se ha cliccato OK, procediamo con l'attivazione dello strumento
        canvas = self.iface.mapCanvas()
        
        # Crea lo strumento di selezione rettangolare
        self.extent_tool = QgsMapToolExtent(canvas)
        
        # Cambia il cursore (es. un mirino) per far capire che si deve disegnare
        self.extent_tool.setCursor(Qt.CrossCursor) 

        # Quando l'utente rilascia il mouse e l'estensione è pronta, lancia la fase 2
        self.extent_tool.extentChanged.connect(self.apri_vista_3d_ritagliata)
        
        # Imposta lo strumento come attivo sulla mappa
        canvas.setMapTool(self.extent_tool)
        



    def apri_vista_3d_ritagliata(self, extent):
        """Fase 2: Apre la mappa 3D applicando l'estensione disegnata"""
        
        # 1. Disattiva lo strumento di selezione e torna al cursore standard (Pan)
        self.iface.mapCanvas().unsetMapTool(self.extent_tool)
        
        # 2. Controllo di sicurezza: se l'utente fa un clic singolo (area nulla), annulliamo
        # isEmpty() controlla se il rettangolo è nullo o malformato, area() controlla l'estensione
        if extent.isEmpty() or extent.width() == 0 or extent.height() == 0:
            # Avvisa l'utente del perché non succede nulla
            QMessageBox.warning(
                self.iface.mainWindow(),
                "3D Map View",
                self.tr("Clic singolo rilevato. Devi cliccare e trascinare per disegnare un rettangolo.\n\nOperazione annullata."),
            )
            return # Esce dalla funzione senza creare la mappa 3D

        # --- 2.5 PULIZIA DI UNA EVENTUALE VISTA 3D PRECEDENTE ---
        if getattr(self, 'canvas_3d', None) is not None:
            try:
                self.canvas_3d.destroyed.disconnect()
            except (TypeError, RuntimeError):
                pass  
        self.ripristina_filtri_ifcspace(mostra_messaggio=False)

        
        # --- 3. APPLICAZIONE FILTRO TEMPORANEO ---
        # Creiamo un dizionario per salvare i filtri precedenti prima di modificarli
        if not hasattr(self, 'filtri_originali_3d') or self.filtri_originali_3d is None:
            self.filtri_originali_3d = {}

        if getattr(self, 'nascondi_ifcspace', False):
            filter_str = "\"IfcClass\" != 'IfcSpace'"
            layers = self.iface.mapCanvas().layers()
            for layer in layers:
                if isinstance(layer, QgsVectorLayer) and layer.fields().indexOf("IfcClass") != -1:
                    # SALVA LA SELEZIONE PRIMA DEL FILTRO
                    id_selezionati = layer.selectedFeatureIds()
                    subset = layer.subsetString()

                    # Se il subset contiene già il NOSTRO filtro, è un residuo di una  sessione precedente: non va salvato come "originale"
                    if filter_str in subset:
                        continue

                    # Salva lo stato attuale SENZA sovrascrivere un originale già salvato
                    if layer.id() not in self.filtri_originali_3d:
                        self.filtri_originali_3d[layer.id()] = subset

                    # Applichiamo il filtro per escludere gli IfcSpace
                    if subset:
                        # Evita di aggiungerlo se l'utente lo aveva già scritto a mano
                        if "IfcSpace" not in subset:
                            layer.setSubsetString(f"({subset}) AND {filter_str}")
                    else:
                        layer.setSubsetString(filter_str)

                    # RIPRISTINA LA SELEZIONE DOPO IL RESET DEL LAYER
                    if id_selezionati:
                        layer.selectByIds(id_selezionati)
        
        # imposta nome vista 
        nome_vista = "IFC 3D View"

        # ---> GESTIONE PULITA DEL PROGETTO <---
        project = QgsProject.instance()
        
        # Rimuoviamo la vecchia vista "IFC 3D View" dal manager prima di crearne una nuova
        if hasattr(project, 'viewsManager'):
            manager = project.viewsManager()
            if hasattr(manager, 'remove3DView'):
                # Rimuove chirurgicamente solo la nostra vista, lasciando intatte quelle dell'utente
                manager.remove3DView(nome_vista)
        
        # 3. Crea la mappa 3D nativa
        self.canvas_3d = self.iface.createNewMapCanvas3D(nome_vista)
        
        # 4. Applica il ritaglio e l'inquadratura
        if self.canvas_3d:

            try:
                # Recupera le impostazioni del 3D
                settings_3d = self.canvas_3d.mapSettings()
                
                # Questa è la funzione che "ritaglia" fisicamente la scena rispetto alla Bounding Box
                settings_3d.setExtent(extent)
                
                # Per ottimizzare l'esperienza, punta la telecamera direttamente sull'area
                self.canvas_3d.scene().viewZoomFull()
                 
            except AttributeError:
                QMessageBox.warning(self.iface.mainWindow(), "3D Map View", self.tr("La tua versione di QGIS non supporta il ritaglio 3D. Aggiorna ad una versione superiore per questa funzionalità."))
            
            self.canvas_3d.destroyed.connect(lambda: QTimer.singleShot(0, self.ripristina_filtri_ifcspace))


    
    # togli i filtri applicati agli IfcSpace quando chiudi la vista 3D, in modo da non lasciare modifiche permanenti sui layer 2D
    def ripristina_filtri_ifcspace(self, mostra_messaggio=True):
        """Fase 3: Ripristina i layer 2D in automatico quando chiudi la vista 3D"""
        
        if hasattr(self, 'filtri_originali_3d') and self.filtri_originali_3d:
            
            # Ripristina ogni layer esattamente al suo stato originale
            for layer_id, filtro_orig in self.filtri_originali_3d.items():
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    # SALVA LA SELEZIONE PRIMA DI RIMUOVERE IL FILTRO
                    id_selezionati_correnti = layer.selectedFeatureIds()

                    layer.setSubsetString(filtro_orig)

                    # RIPRISTINA LA SELEZIONE ADESSO CHE IL LAYER È PULITO
                    if id_selezionati_correnti:
                        layer.selectByIds(id_selezionati_correnti)
            
            # Svuotiamo il dizionario
            self.filtri_originali_3d.clear()
            
            # Messaggio di conferma (solo alla chiusura vera della mappa 3D)
            if mostra_messaggio:
                self.iface.messageBar().pushMessage(
                    "3D Map View", 
                    self.tr("Mappa 3D chiusa. I filtri originali sono stati ripristinati."), 
                    level=Qgis.Success, 
                    duration=3
                )
        
        # Pulisce il riferimento al canvas per evitare memory leak
        self.canvas_3d = None

            
    #------------------------------------------------------------------------------------------------








    def run_properties(self):
        if not self.properties_dialog:
            self.properties_dialog = IFCPropertiesDialog(self.iface, parent=self.iface.mainWindow())
            # ObjectName univoco per permettere a QGIS di salvare lo stato della UI
            self.properties_dialog.setObjectName("IfcSqlPropertiesDock")
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.properties_dialog)

        # Popola le combo box con le connessioni esistenti prima di mostrare la UI
        self.properties_dialog.populate_connection_combo_MSSQL()
        self.properties_dialog.populate_connection_combo_PostgreSQL()
        
        # Mostra la finestra
        self.properties_dialog.show() 
        
        # Forza l'aggancio intelligente a schede
        self.force_tabify_properties_dock()
        
        # Porta in primo piano la scheda appena creata
        self.properties_dialog.raise_()














    


















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
        QMessageBox.critical(self, self.tr("Errore"), message)
    
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

    # Funzione per eseguire l'importazione tramite eseguibile precompilato

    def esegui_importazione_exe(self, file_path, server_host, schema_version, progress_dialog):
        """
        Lancia gli eseguibili precompilati (Import_IFC4.exe o Import_IFC4X3.exe)
        presenti nella cartella IfcSQL del plugin.
        """
        # 1. Determina percorsi
        plugin_dir = os.path.dirname(__file__)
        exe_folder = os.path.join(plugin_dir, "IfcSQL_scripts")
        
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
        progress_dialog.setLabelText(self.tr("Importazione in corso con {exe_name}.\nL'operazione potrebbe richiedere alcuni minuti...\n\nAspetta anche se QGIS sembra bloccato.").format(exe_name=exe_name))
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




    def convert_ifc_to_wkt_in_memory(self, elements_to_convert, spaces_to_convert, easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate, progress_dialog):
        """
        Estrae le geometrie IFC direttamente in RAM usando ifcopenshell.geom,
        applica la georeferenziazione e genera il WKT 3D (Multipolygon Z).
        """
        log_report = [self.tr("--- Conversione IFC in WKT ---\n")]
        
        # Uniamo tutti gli elementi in una singola lista
        all_elements = elements_to_convert + spaces_to_convert
        total_elements = len(all_elements)
        
        log_report.append(self.tr("Elementi totali da processare: {tot}\n").format(tot=total_elements))

        log_report.append(self.tr("Nota: vengono processati gli IfcElement e gli IfcSpace, mentre sono esclusi gli IfcOpeningElement.\n"))

        # Configurazione ifcopenshell.geom
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True) 

        element_wkts = {}
        successi = 0
        fallimenti = 0

        # LISTA PER MEMORIZZARE I DETTAGLI DEGLI ERRORI
        dettaglio_fallimenti = []
        
        # Variabile per controllare l'annullamento
        operation_aborted = False

        for i, el in enumerate(all_elements):
            # 1. Aggiornamento progress bar e anti-freeze QGIS (Batching visivo ogni 50 elementi)
            if i % 50 == 0:
                progress_dialog.setValue(i)
                QApplication.processEvents()
                
                if progress_dialog.wasCanceled():
                    log_report.append(self.tr("\nOPERAZIONE ANNULLATA DALL'UTENTE."))
                    operation_aborted = True
                    break

            class_name = el.is_a()
            global_id = el.GlobalId

            try:
                # 2. Creazione geometria in RAM
                shape = ifcopenshell.geom.create_shape(settings, el)
                
                # 3. Estrazione vertici e facce
                verts = np.array(shape.geometry.verts).reshape(-1, 3)
                faces = np.array(shape.geometry.faces).reshape(-1, 3)

                # 4. Traslazione e Rotazione (Georeferenziazione)
                if all(v is not None for v in [easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate]):
                    theta = atan2(x_axis_ordinate, x_axis_abscissa)
                    rot_matrix = np.array([
                        [cos(theta), -sin(theta), 0],
                        [sin(theta),  cos(theta), 0],
                        [0,           0,          1]
                    ])
                    # Applica rotazione e traslazione
                    verts = np.dot(verts, rot_matrix.T)
                    verts += np.array([easting, northing, orthogonal_height])
                
                # 5. Arrotondamento per pulizia
                rounded_vertices = np.round(verts, decimals=5)
                multipolygon_coords = []
                
                # Contatore per le facce degenerate
                removed_faces_count = 0

                for face in faces:
                    coords = [tuple(rounded_vertices[idx]) for idx in face]
                    # Salta facce degeneri (meno di 3 vertici unici)
                    if len(set(coords)) < 3:
                        removed_faces_count += 1
                        continue
                    # Chiudi il ring (primo vertice == ultimo vertice)
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    
                    multipolygon_coords.append([coords])
                
                if removed_faces_count > 0:
                    log_report.append(self.tr("\n--- Errore facce degenerate---\n"))
                    log_report.append(self.tr("Rimosse {removed_faces_count} facce degenerate nell'elemento {class_name} (GlobalId: {global_id}).\n").format(
                        removed_faces_count=removed_faces_count, class_name=class_name, global_id=global_id))
                    log_report.append(self.tr("Gli elementi con facce degenerate potrebbero non essere visualizzati correttamente.\n"))

                # 6. Creazione stringa WKT
                if multipolygon_coords:
                    wkt = "MULTIPOLYGON Z ("
                    face_strings = []
                    for poly in multipolygon_coords:
                        ring_strings = []
                        for ring in poly:
                            ring_str = ", ".join(f"{x} {y} {z}" for x, y, z in ring)
                            ring_strings.append(f"({ring_str})")
                        face_strings.append(f"({', '.join(ring_strings)})")
                    wkt += ", ".join(face_strings) + ")"
                    
                    element_wkts[(class_name, global_id)] = wkt
                    successi += 1
                else:
                    element_wkts[(class_name, global_id)] = None
                    fallimenti += 1
                    dettaglio_fallimenti.append((class_name, global_id, self.tr("Geometria scartata, nessuna faccia valida.")))

            except Exception as e:
                # Geometria non esistente o errore di Open CASCADE
                element_wkts[(class_name, global_id)] = None
                fallimenti += 1

                # Puliamo l'errore se è troppo lungo e lo aggiungiamo alla lista
                error_msg = str(e).strip()
                if not error_msg:
                    error_msg = self.tr("Nessuna rappresentazione 3D trovata per questo elemento.")
                
                dettaglio_fallimenti.append((class_name, global_id, error_msg))

        if operation_aborted:
            return False, element_wkts, log_report

        progress_dialog.setValue(total_elements)

        log_report.append(self.tr("\n--- Riepilogo Conversione ---\n"))
        log_report.append(self.tr("Elementi elaborati con successo: {succ}").format(succ=successi))
        log_report.append(self.tr("Elementi senza geometria o falliti: {fail}").format(fail=fallimenti))
        
        if dettaglio_fallimenti:
            log_report.append(self.tr("\n--- DETTAGLIO ERRORI E FALLIMENTI ---\n"))
            log_report.append(self.tr("ATTENZIONE: Alcuni elementi (esempio: IfcStair, IfcRoof, IfcCurtainWall, ecc.) potrebbero non avere una propria geometria e quindi la conversione potrebbe fallire.\n"))
            log_report.append(self.tr("Altri elementi invece potrebbero fallire per geometria difettosa.\n\n"))


            # Ordiniamo per classe per una lettura più chiara
            dettaglio_fallimenti.sort(key=lambda x: x[0])
            
            for class_name, gid, err_msg in dettaglio_fallimenti:
                log_report.append(self.tr("  -> Classe: {class_name} | GlobalId: {gid} | Errore: {err}\n").format(
                    class_name=class_name, 
                    gid=gid, 
                    err=err_msg
                ))

        return True, element_wkts, log_report






    
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
        
        # Creiamo e mostriamo SUBITO la barra di caricamento
        total_items = len(element_wkts)
        progress_dialog_db = QProgressDialog(
            self.tr("Connessione e preparazione dati in corso..."), # Testo iniziale
            self.tr("Annulla"), 
            0, 
            total_items, 
            self.iface.mainWindow()
        )
        progress_dialog_db.setWindowTitle(self.tr("Inserimento Database"))
        progress_dialog_db.setWindowModality(Qt.WindowModal)
        progress_dialog_db.setMinimumDuration(0) # Elimina ritardi Qt
        progress_dialog_db.show()                # Mostra la finestra
        QApplication.processEvents()             # Forza QGIS a disegnarla immediatamente


        try:
            #self.iface.messageBar().pushMessage("Info", "Connessione a PostgreSQL...", level=Qgis.Info, duration=3)
            # Connect to the PostgreSQL database
            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()
            log_report.append(self.tr("Inserimento dati per Progetto:\n'{project_name}' (ID: {project_id})").format(project_name=project_name, project_id=project_id))

            # --- Recupera i mapping per QUESTO specifico ProjectId ---
            #log_report.append(self.tr("\nRecupero mapping GlobalId per ProjectId {project_id}\n").format(project_id=project_id))

            # Estraiamo tutti i GlobalId necessari dal dizionario degli elementi
            global_ids = [gid for cls, gid in element_wkts.keys()]
            value_to_entityid = {}

            if not global_ids:
                log_report.append(self.tr("ATTENZIONE: Nessun GlobalId da cercare."))
            else:
                # Interroghiamo il database a blocchi (batch) per evitare query troppo pesanti per l'ODBC
                BATCH_SIZE = 500
                for i in range(0, len(global_ids), BATCH_SIZE):
                    batch_gids = tuple(global_ids[i:i+BATCH_SIZE])
                    
                    # La clausola IN %s obbliga il Foreign Data Wrapper a filtrare direttamente su MSSQL.
                    # I GlobalId sono stringhe ASCII sicure, così evitiamo che Postgres legga stringhe con 
                    # caratteri speciali (es. 'à', '°') che causano l'errore di codifica UTF8 0xdf.
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
                            AND t1."Value" IN %s
                            AND t1."OrdinalPosition" = 1
                    """, (project_id, batch_gids))

                    for entity_id, value in cursor.fetchall():
                        value_to_entityid[value] = entity_id

            if not value_to_entityid:
                log_report.append(self.tr("ATTENZIONE: Nessun mapping GlobalId trovato."))

            # --- Insert data into postgres ---
            log_report.append(self.tr("\nInserimento geometrie in 'ifcgeometry.entitygeometry'\n"))
           
            # Aggiorniamo il testo della barra per la nuova fase
            progress_dialog_db.setLabelText(self.tr("Inserimento geometrie nel Database..."))
            QApplication.processEvents()
            
            inserted_count = 0
            skipped_count = 0
            failed_count = 0
            operation_aborted = False

            BATCH_SIZE = 1000

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

                # --- IL TRUCCO DEL BATCHING PER SALVARE LA MEMORIA ---
                # Se il numero di elementi elaborati è un multiplo di BATCH_SIZE...
                if (i + 1) % BATCH_SIZE == 0:
                    conn.commit()  # <-- QUESTO azzera la memoria dei lock in Postgres!

            progress_dialog_db.close()

            if operation_aborted:
                conn.rollback()
                return False, log_report
            
            # --- 4. Commit e riepilogo ---
            
            conn.commit()
            
            log_report.append(self.tr("Righe inserite con successo: {inserted_count}\n").format(inserted_count=inserted_count))
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
        progress.resize(450, 120)      # Diamo una dimensione 
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

                if import_name == 'ifcopenshell':
                    importlib.import_module('ifcopenshell.geom')
                
                if import_name == 'pyodbc':
                    try: globals()['pyodbc'].pooling = False
                    except Exception: pass

                # Aggiorna i flag globali
                if import_name == 'ifcopenshell': globals()['IFCOPENSHELL_PRESENTE'] = True
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

        # Controlla e installa automaticamente le librerie mancanti
        if not self.check_and_install_dependencies():
            return 

        # 2. Carica il file IFC
        try:
            ifc = ifcopenshell.open(ifc_file_path)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore"), self.tr("Impossibile aprire il file IFC:\n{e}").format(e=e))
            return
        
        # --- ESTRAZIONE DATI GEOREFERENZIAZIONE ---
        try:
            epsg_code, easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate = self.extract_IFC_CRS(ifc)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore"), self.tr("Impossibile estrarre i dati CRS: {e}").format(e=e))
            return
        
        # Filtriamo gli elementi
        elements = ifc.by_type("IfcElement")
        spaces = ifc.by_type("IfcSpace")
        skip_types = {"IfcOpeningElement"}
        elements_to_convert = [el for el in elements if el.is_a() not in skip_types]
        spaces_to_convert = [sp for sp in spaces if sp.is_a() not in skip_types]
        
        total_steps = len(elements_to_convert) + len(spaces_to_convert)
        
        if total_steps == 0:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Nessun IfcElement o IfcSpace valido trovato nel file IFC."))
            return

        # Nascondiamo la finestra principale
        self.hide()

        # Creiamo e configuriamo la QProgressDialog
        progress_dialog = QProgressDialog(
            self.tr("Estrazione geometria IFC e generazione WKT in corso...\nAttendere prego..."), 
            self.tr("Annulla"), 
            0, 
            total_steps, 
            self.iface.mainWindow()
        )
        progress_dialog.setWindowTitle(self.tr("Conversione IFC in WKT"))
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.show()

        # ============================================
        # FASE UNICA: ESTRAZIONE GEOMETRIA E CREAZIONE WKT
        # ============================================
        try:
            success_wkt, element_wkts, log_report_wkt = self.convert_ifc_to_wkt_in_memory(
                elements_to_convert, spaces_to_convert, 
                easting, northing, orthogonal_height, x_axis_abscissa, x_axis_ordinate, 
                progress_dialog
            )
            
            progress_dialog.close()

            summary_message_wkt = "\n".join(log_report_wkt)
            msgBox_wkt = QMessageBox(self.iface.mainWindow())
            msgBox_wkt.setWindowTitle(self.tr("Riepilogo Conversione WKT"))
            msgBox_wkt.setDetailedText(summary_message_wkt)

            if not success_wkt:
                msgBox_wkt.setText(self.tr("Conversione Interrotta o Fallita."))
                msgBox_wkt.setIcon(QMessageBox.Critical)
                msgBox_wkt.exec_()
                return # STOP procedura
            
            if not element_wkts or all(v is None for v in element_wkts.values()):
                msgBox_wkt.setText(self.tr("Nessun dato WKT valido generato. Impossibile proseguire."))
                msgBox_wkt.setIcon(QMessageBox.Warning)
                msgBox_wkt.exec_()
                return # STOP procedura

            msgBox_wkt.setText(self.tr("Conversione WKT completata con successo."))
            msgBox_wkt.setIcon(QMessageBox.Information)
            msgBox_wkt.setStandardButtons(QMessageBox.Ok)
            msgBox_wkt.exec_()

        except Exception as e:
            progress_dialog.close()
            QMessageBox.critical(self, self.tr("Errore Critico Conversione"), self.tr("Errore durante elaborazione geometrica:\n{e}").format(e=e))
            self.close()
            return

        # ========================================
        # INSERIMENTO POSTGRESQL
        # ========================================
        try:
            if not hasattr(self, '_postgresql_conn_params'):
                QMessageBox.critical(self, self.tr("Attenzione"), self.tr("Parametri DB persi. Riconnettiti."))
                return

            host, dbname, user, password, port = self._postgresql_conn_params
            db_params = {"host": host, "dbname": dbname, "user": user, "password": password, "port": port}
            
            # Qui passi `element_wkts` esattamente come facevi prima!
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
            msgBox_db.exec_()
            
            self.close()

        except Exception as e:
            QMessageBox.critical(self, self.tr("Errore Critico DB"), self.tr("Errore durante inserimento DB:\n{e}").format(e=e))
            self.close()
            return
        
        # --- AGGIORNAMENTO MV dei progetti in BACKGROUND ---
        def refresh_mv_task(params):
            try:
                conn = psycopg2.connect(
                    host=params[0], database=params[1], 
                    user=params[2], password=params[3], port=params[4]
                )
                cur = conn.cursor()
                cur.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY ifcproject.projectpostgres;')
                conn.commit()
                cur.close()
                conn.close()
                QgsMessageLog.logMessage("Materialized View aggiornata con successo.", "ifcSQL", Qgis.Info)
            except Exception as e:
                QgsMessageLog.logMessage(f"Refresh MV fallito: {e}", "ifcSQL", Qgis.Critical)

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
        self.pushButton_NuovaConnessionePostgreSQL.clicked.connect(self.create_new_connection_PostgreSQL)
        
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
            log_formatted("STEP 3/8", self.tr("Disabilitazione vincoli..."))
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
                
                #Salva il numero di righe eliminate in PostgreSQL
                count_entities_pg = cursor_pg.rowcount
                
                conn_pg.commit()
            finally:
                conn_pg.close()

            progress.setValue(100)
            QApplication.restoreOverrideCursor()
            progress.close()
            QMessageBox.information(self, self.tr("Successo"), self.tr("Eliminazione del progetto completata con successo.\n Entità rimosse da MSSQL: {count_entities}.\n Entità rimosse da PostgreSQL: {count_entities_pg}.").format(count_entities=count_entities, count_entities_pg=count_entities_pg))
            
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















                                                                                           


#  ███████ ██ ██      ███████ ███████ ██████       ██████ ██       █████  ███████ ███████
#  ██      ██ ██        ██    ██      ██  ██      ██      ██      ██   ██ ██      ██     
#  █████   ██ ██        ██    █████   ██████      ██      ██      ███████ ███████ ███████
#  ██      ██ ██        ██    ██      ██  ██      ██      ██      ██   ██      ██      ██
#  ██      ██ ███████   ██    ███████ ██  ██       ██████ ███████ ██   ██ ███████ ███████











#######################################################################
## Classe per la finestra di dialogo delle query
#######################################################################
        

class QueryDialog(Ui_Filter, QDockWidget):
    def __init__(self, iface, parent=None):
        super(QueryDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # Questo è l'ID univoco che serve al codice per trovare ed eliminare i duplicati
        self.setObjectName("IfcSqlQueryDock")

        # Inizializza il LED grigio
        self.set_led_color("gray")
        
        # Pulsanti gestione connessione DB (MSSQL + PostgreSQL)
        self.comboBox_Connessione.currentIndexChanged.connect(self.reset_ui_on_connection_change_PostgreSQL_Query)
        self.comboBox_MSSQL.currentIndexChanged.connect(self.reset_ui_on_connection_change_MSSQL_Query)
        self.pushButton_NuovaConnessione.clicked.connect(self.create_new_connection_PostgreSQL_Query)
        self.pushButton_NuovaConnessioneMSSQL.clicked.connect(self.create_new_connection_MSSQL_Query)
        # Un solo pulsante connette entrambi i database contemporaneamente
        self.pushButton_ConnettiDB.clicked.connect(self.connect_both_databases_Query)
        

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

    # stesse funzioni per MSSQL
    def reset_ui_on_connection_change_MSSQL_Query(self):
        """Resetta il LED e l'etichetta quando la selezione della connessione MSSQL cambia."""
        self.set_led_color("gray")
        self.label_led.setText(self.tr("Seleziona e connetti"))
        if hasattr(self, '_mssql_conn_params'):
            del self._mssql_conn_params

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

    def populate_connection_combo_MSSQL_Query(self):
        self.comboBox_MSSQL.clear()
        settings = QSettings()
        settings.beginGroup('MSSQL/connections')
        connections = settings.childGroups()
        self.comboBox_MSSQL.addItems(connections)

    def create_new_connection_MSSQL_Query(self):
        self.iface.openDataSourceManagerPage("mssql")



    # FUNZIONE PER VERIFICARE L'ALLINEAMENTO DEI DATABASE CONFRONTANDO I GUID (MSSQL vs Postgres)
    def verify_database_alignment_Query(self):
        """Verifica l'allineamento confrontando i GUID dei due database target."""
        guid_direct_mssql = None
        try:
            host, db, user, pwd = self._mssql_conn_params
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host};DATABASE={db};TrustServerCertificate=yes;"
            if user and str(user).strip():
                conn_str += f"UID={user};PWD={pwd};"
            else:
                conn_str += "Trusted_Connection=yes;"
            conn = pyodbc.connect(conn_str, timeout=15)
            cursor = conn.cursor()
            cursor.execute("SELECT service_broker_guid FROM sys.databases WHERE name = 'ifcSQL'")
            row = cursor.fetchone()
            if row:
                guid_direct_mssql = str(row[0])
            conn.close()
            if not guid_direct_mssql:
                return False, self.tr("Impossibile recuperare GUID dal DB MSSQL (ifcSQL).")
        except Exception as e:
            return False, self.tr("Errore lettura GUID MSSQL Diretto: {error}").format(error=str(e))

        guid_via_postgres = None
        try:
            h_pg, db_pg, u_pg, p_pg, port_pg = self._postgresql_conn_params
            conn_pg = psycopg2.connect(host=h_pg, database=db_pg, user=u_pg, password=p_pg, port=port_pg)
            cursor_pg = conn_pg.cursor()
            cursor_pg.execute("SELECT db_guid FROM public.mssql_identity_card")
            row_pg = cursor_pg.fetchone()
            conn_pg.close()
            if row_pg and row_pg[0]:
                guid_via_postgres = str(row_pg[0])
            else:
                return False, self.tr("La tabella 'public.mssql_identity_card' in Postgres è vuota o non accessibile.")
        except Exception as e:
            return False, self.tr("Errore leggendo 'mssql_identity_card' da Postgres:\n\n{error}").format(error=str(e))

        if guid_direct_mssql.strip().lower() == guid_via_postgres.strip().lower():
            return True, self.tr("OK")
        else:
            return False, (self.tr("DISALLINEAMENTO DATABASE!\n\n1. GUID MSSQL (QGIS): {guid_ms}\n2. GUID MSSQL (visto da PG): {guid_pg}\n\nPostgreSQL è collegato a un database MSSQL diverso da quello selezionato.").format(guid_ms=guid_direct_mssql, guid_pg=guid_via_postgres))

    def connect_both_databases_Query(self):
        self.mssql_ready = False
        self.postgres_ready = False
        self.connection_errors = []
        self.set_led_color("#ffd700")
        self.label_led.setText(self.tr("Connessione in corso..."))
        self.pushButton_ConnettiDB.setEnabled(False)
        self.connect_selected_DB_MSSQL_Query()
        self.connect_selected_DB_PostgreSQL_Query()

    def connect_selected_DB_MSSQL_Query(self):
        selected_connection = self.comboBox_MSSQL.currentText()
        if hasattr(self, '_mssql_conn_params'): del self._mssql_conn_params
        if not selected_connection:
            self.on_mssql_error_Query(self.tr("Nessuna connessione MSSQL selezionata"))
            return
        settings = QSettings()
        settings.beginGroup(f"MSSQL/connections/{selected_connection}")
        host = settings.value("host")
        database = settings.value("database")
        username = settings.value("username")
        password = settings.value("password")
        settings.endGroup()
        if not host or not database:
            self.on_mssql_error_Query(self.tr("Parametri MSSQL mancanti"))
            return
        self.ms_thread = MssqlConnectionThread(host, database, username, password)
        self.ms_thread.success.connect(self.on_mssql_connected_Query)
        self.ms_thread.error.connect(self.on_mssql_error_Query)
        self.ms_thread.start()

    def connect_selected_DB_PostgreSQL_Query(self):
        selected_connection = self.comboBox_Connessione.currentText()
        if hasattr(self, '_postgresql_conn_params'): del self._postgresql_conn_params
        if not selected_connection:
            self.on_pg_error_Query(self.tr("Nessuna connessione PostgreSQL selezionata"))
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
            self.on_pg_error_Query(self.tr("Parametri PostgreSQL mancanti"))
            return
        self.pg_thread = PostgresConnectionThread(host, database, username, password, port)
        self.pg_thread.success.connect(self.on_pg_connected_Query)
        self.pg_thread.error.connect(self.on_pg_error_Query)
        self.pg_thread.start()

    def on_mssql_connected_Query(self, params):
        self._mssql_conn_params = params
        self.mssql_ready = True
        self.check_if_both_ready_Query()

    def on_mssql_error_Query(self, err_msg):
        self.connection_errors.append(f"MSSQL: {err_msg}")
        self.check_if_both_ready_Query()

    def on_pg_connected_Query(self, params):
        self._postgresql_conn_params = params
        self.postgres_ready = True
        self.check_if_both_ready_Query()

    def on_pg_error_Query(self, err_msg):
        self.connection_errors.append(f"PostgreSQL: {err_msg}")
        self.check_if_both_ready_Query()

    def check_if_both_ready_Query(self):
        mssql_finished = self.mssql_ready or any("MSSQL" in e for e in self.connection_errors)
        pg_finished = self.postgres_ready or any("PostgreSQL" in e for e in self.connection_errors)
        if not (mssql_finished and pg_finished):
            return
        if self.connection_errors:
            self.set_led_color("#fa3e3e")
            self.label_led.setText(self.tr("Errore Connessione"))
            self.pushButton_ConnettiDB.setEnabled(True)
            QMessageBox.critical(self, self.tr("Errore di Connessione"), "\n\n".join(self.connection_errors))
            return
        try:
            is_aligned, error_message = self.verify_database_alignment_Query()
            if is_aligned:
                self.set_led_color("#90ee90")
                self.label_led.setText(self.tr("Connessi e Allineati"))
                self.populate_territory_tables()
                if self.stackedWidget.currentIndex() == 2:
                    self.populate_project_list()
            else:
                self.set_led_color("#fa3e3e")
                self.label_led.setText(self.tr("Errore Allineamento DB!"))
                QMessageBox.critical(self, self.tr("Disallineamento Database"),
                                     self.tr("Verifica fallita:\n\n{error_message}").format(error_message=error_message))
                if hasattr(self, '_mssql_conn_params'): del self._mssql_conn_params
                if hasattr(self, '_postgresql_conn_params'): del self._postgresql_conn_params
        except Exception as e:
            self.set_led_color("#fa3e3e")
            self.label_led.setText(self.tr("Errore imprevisto"))
            QMessageBox.critical(self, self.tr("Errore Script"), self.tr("Eccezione durante la verifica:\n{error}").format(error=str(e)))
        finally:
            self.pushButton_ConnettiDB.setEnabled(True)
    

    # Funzione chiamata alla chiusura del dock
    def closeEvent(self, event):
        # Esegue un reset completo dei filtri
        self.reset_predefined_filters(hard_reset=True)
        # 1. Resetta i filtri delle aree PAGINA 1 (Hard Reset)
        self.reset_predefined_filters(hard_reset=True)
        # 2. Resetta la logica interna della connessione (LED grigio e params)
        self.reset_ui_on_connection_change_PostgreSQL_Query()
        self.reset_ui_on_connection_change_MSSQL_Query()
        

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
            self.listWidget_PianoIFC.clear()  # Svuota la lista dei piani
            self.lineEdit_PianoIFC.clear()    # Svuota la barra di ricerca dei piani

            self.listWidget_PianoIFC_2.clear()
            self.lineEdit_PianoIFC_2.clear()
            self.listWidget_ClasseIFC_2.clear()
            self.lineEdit_ClasseIFC_2.clear()
            


 





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
            if not hasattr(self, '_postgresql_conn_params') or not hasattr(self, '_mssql_conn_params'):
                QMessageBox.warning(
                    self, 
                    self.tr("Database non connesso"), 
                    self.tr("Attenzione: Non sei connesso ai database.\n\nÈ necessario connettersi prima di selezionare un'area, altrimenti non sarà possibile recuperare le classi IFC contenute nella selezione."
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

                # --- AGGIORNA LE LISTE IFC (CLASSI E PIANI) SUBITO ---
                self.populate_available_ifc_classes()
                self.populate_available_ifc_storeys()

            # Caso B: L'utente dice SI, ma la geometria è invalida
            else:
                QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Area non valida o non chiusa (servono almeno 3 punti)."))
                self.reset_mini_map() # Resetta se non valido

                # --- Aggiorna la lista IFC (La svuota perché non c'è geometria) ---
                self.populate_available_ifc_classes()
                self.populate_available_ifc_storeys()

        # Caso C: L'utente dice NO (Annulla)
        else:
            self.reset_mini_map() # Resetta se annullato

            # --- Aggiorna la lista (La svuota perché non c'è geometria) ---
            self.populate_available_ifc_classes()
            self.populate_available_ifc_storeys()


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
        self.comboBox_SelezionaFIltroIFC.addItem(self.tr("Filtro Piano IFC"), 1)         # page_2_FiltroPianoIFC  (index 1)
        self.comboBox_SelezionaFIltroIFC.addItem(self.tr("Filtro Classe e Piano IFC"), 2) # page_3_FiltroDoppio    (index 2)


        # Collega il segnale
        self.comboBox_SelezionaFIltroIFC.currentIndexChanged.connect(self.change_ifc_page)
        
        # Imposta pagina iniziale
        self.change_ifc_page(0)

        # BARRE DI RICERCA TESTUALE
        self.lineEdit_ClasseIFC.textChanged.connect(self.filter_ifc_list)
        self.lineEdit_PianoIFC.textChanged.connect(self.filter_storey_list)
        
        # --- AGGIUNTE PER PAGINA 3 (FILTRO DOPPIO) ---
        self.lineEdit_PianoIFC_2.textChanged.connect(self.filter_storey_list_2)
        self.lineEdit_ClasseIFC_2.textChanged.connect(self.filter_class_list_2)
        
        # Rileva quando l'utente seleziona/deseleziona un piano nella terza tab per aggiornare le classi relative
        self.listWidget_PianoIFC_2.itemChanged.connect(self.populate_double_filter_classes)

        # Aggiorna i piani (di entrambe le liste) quando cambiano i filtri del contesto geografico o progettuale
        self.comboBox_SelezionaArea.checkedItemsChanged.connect(self.populate_available_ifc_storeys)
        self.groupBox_2_FiltroContesto.toggled.connect(self.populate_available_ifc_storeys)
        self.list_Progetti.itemChanged.connect(self.populate_available_ifc_storeys)
        

    def change_ifc_page(self, index):
        """Cambia la pagina visibile nello stackedWidget IFC."""
        page_idx = self.comboBox_SelezionaFIltroIFC.itemData(index)
        if page_idx is not None:
            self.stackedWidget_IFC.setCurrentIndex(page_idx)

    
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
    # Funzioni pagina 2 - Filtro piano IFC

    def populate_available_ifc_storeys(self):
        """
        Popola le liste dei piani (Tab 2 e Tab 3) estratti da MSSQL
        mostrando SOLO i piani che hanno elementi con geometria reale 
        nel contesto spaziale o progettuale selezionato.
        """
        self.listWidget_PianoIFC.clear()
        self.listWidget_PianoIFC_2.clear()
        self.listWidget_ClasseIFC_2.clear()

        # Inserisce la scritta segnaposto iniziale nella lista delle classi del filtro doppio
        placeholder_item = QListWidgetItem(self.tr("Seleziona un piano per caricare le classi relative"))
        placeholder_item.setFlags(Qt.NoItemFlags)
        font = placeholder_item.font()
        font.setItalic(True)
        placeholder_item.setFont(font)
        placeholder_item.setForeground(QColor("gray"))
        self.listWidget_ClasseIFC_2.addItem(placeholder_item)

        if not hasattr(self, '_postgresql_conn_params') or not hasattr(self, '_mssql_conn_params'):
            return

        use_context = self.groupBox_2_FiltroContesto.isChecked()
        current_page_idx = self.stackedWidget.currentIndex() if use_context else -1
        
        project_names = []
        active_ids = set()

        try:
            conn_pg = self._get_db_connection()
            if not conn_pg: return
            cur_pg = conn_pg.cursor()
            
            # --- FASE 1: Estrazione ID attivi e Nomi Progetto da PostgreSQL ---
            if use_context:
                if current_page_idx == 0:  # Filtro Geografico Predefinito (Comuni/Aree)
                    selected_table = self.comboBox_SelezionaTipoArea.currentText()
                    selected_areas = self.comboBox_SelezionaArea.checkedItems()
                    if not selected_table or not selected_areas:
                        cur_pg.close(); conn_pg.close(); return 
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    areas_formatted = ", ".join([f"'{a.replace('\'', '\'\'')}'" for a in selected_areas])
                    query = f"""
                        SELECT g."GlobalId_MSSQL", g."ProjectName" FROM "ifcgeometry"."entitygeometry" g
                        JOIN "territory"."{selected_table}" t ON ST_Within(g."Geometry", t.geom)
                        WHERE t."name" IN ({areas_formatted}) AND g."GlobalId_MSSQL" IS NOT NULL;
                    """
                    cur_pg.execute(query)
                    rows_pg = cur_pg.fetchall()
                    active_ids = set(row[0] for row in rows_pg)
                    project_names = list(set(row[1] for row in rows_pg if row[1]))

                elif current_page_idx == 1:  # Filtro Manuale disegnato su mappa
                    if not self.current_area_geometry:
                        cur_pg.close(); conn_pg.close(); return
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    wkt_area = self.current_area_geometry.asWkt()
                    srid = self.iface.mapCanvas().mapSettings().destinationCrs().postgisSrid()
                    query = f"""
                        SELECT g."GlobalId_MSSQL", g."ProjectName" FROM "ifcgeometry"."entitygeometry" g
                        WHERE ST_Intersects(g."Geometry", ST_GeomFromText('{wkt_area}', {srid})) AND g."GlobalId_MSSQL" IS NOT NULL;
                    """
                    cur_pg.execute(query)
                    rows_pg = cur_pg.fetchall()
                    active_ids = set(row[0] for row in rows_pg)
                    project_names = list(set(row[1] for row in rows_pg if row[1]))

                elif current_page_idx == 2:  # Filtro Progetto esplicito
                    for i in range(self.list_Progetti.count()):
                        item = self.list_Progetti.item(i)
                        if item.checkState() == Qt.Checked and not item.isHidden():
                            project_names.append(item.text())
                    if not project_names:
                        cur_pg.close(); conn_pg.close(); return
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    projects_formatted = ", ".join([f"'{p.replace('\'', '\'\'')}'" for p in project_names])
                    query = f"""
                        SELECT g."GlobalId_MSSQL" FROM "ifcgeometry"."entitygeometry" g
                        WHERE g."ProjectName" IN ({projects_formatted}) AND g."GlobalId_MSSQL" IS NOT NULL;
                    """
                    cur_pg.execute(query)
                    active_ids = set(row[0] for row in cur_pg.fetchall())
            else:
                # Se il contesto è disattivato, prendiamo tutti i progetti con almeno una geometria
                QApplication.setOverrideCursor(Qt.WaitCursor)
                query = 'SELECT DISTINCT "ProjectName" FROM ifcgeometry.entitygeometry WHERE "ProjectName" IS NOT NULL;'
                cur_pg.execute(query)
                project_names = [row[0] for row in cur_pg.fetchall()]

            cur_pg.close()
            conn_pg.close()

            if not project_names and not active_ids: return

            # --- FASE 2: Interrogazione Relazionale Piani su MSSQL ---
            host, db, user, pwd = self._mssql_conn_params
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host};DATABASE={db};TrustServerCertificate=yes;"
            if user and str(user).strip(): conn_str += f"UID={user};PWD={pwd};"
            else: conn_str += "Trusted_Connection=yes;"

            conn_ms = pyodbc.connect(conn_str, timeout=15)
            cur_ms = conn_ms.cursor()
            
            projects_formatted = ", ".join([f"'{p.replace('\'', '\'\'')}'" for p in project_names])
            query_ms = f"""
                SELECT DISTINCT relListObj.[Value] AS ElementID, storeyName.[Value] AS NomeLivello
                FROM [ifcProject].[Project] p
                JOIN [ifcProject].[EntityInstanceIdAssignment] assign ON p.ProjectId = assign.ProjectId
                JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj ON assign.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId
                JOIN [ifcInstance].[EntityAttributeOfEntityRef] spatialRef ON spatialRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                JOIN [ifcInstance].[Entity] spatialEntity ON spatialEntity.GlobalEntityInstanceId = spatialRef.[Value]
                JOIN [ifcSchema].[Type] spatialType ON spatialEntity.EntityTypeId = spatialType.TypeId
                JOIN [ifcInstance].[EntityAttributeOfString] storeyName ON storeyName.GlobalEntityInstanceId = spatialRef.[Value] AND storeyName.OrdinalPosition = 3
                WHERE p.ProjectName IN ({projects_formatted})
                  AND spatialType.ExpressName = 'IfcBuildingStorey' -- Sfoltisce gli elementi fantasma
                  AND ((relType.ExpressName = 'IfcRelContainedInSpatialStructure' AND spatialRef.OrdinalPosition = 6)
                       OR (relType.ExpressName = 'IfcRelAggregates' AND spatialRef.OrdinalPosition = 5));
            """

            cur_ms.execute(query_ms)
            
            # --- FASE 3: Filtraggio Incrociato in Memoria (Zero Elementi Fantasma) ---
            storeys_set = set()
            for row in cur_ms.fetchall():
                element_id = row[0]
                storey_name = row[1]
                # Se il contesto è attivo, mostriamo il piano solo se l'ID elemento ha geometria reale nel set
                if not use_context or (element_id in active_ids):
                    if storey_name:
                        storeys_set.add(storey_name)
            
            cur_ms.close()
            conn_ms.close()

            storeys = sorted(list(storeys_set))

            # --- FASE 4: Popolamento interfacce ---
            if storeys:
                self.listWidget_PianoIFC_2.blockSignals(True)
                for storey in storeys:
                    item1 = QListWidgetItem(str(storey))
                    item1.setFlags(item1.flags() | Qt.ItemIsUserCheckable)
                    item1.setCheckState(Qt.Unchecked)
                    self.listWidget_PianoIFC.addItem(item1)

                    item2 = QListWidgetItem(str(storey))
                    item2.setFlags(item2.flags() | Qt.ItemIsUserCheckable)
                    item2.setCheckState(Qt.Unchecked)
                    self.listWidget_PianoIFC_2.addItem(item2)
                self.listWidget_PianoIFC_2.blockSignals(False)

        except Exception as e:
            QgsMessageLog.logMessage(f"Errore caricamento piani IFC filtrati: {str(e)}", "ifcSQL", Qgis.Critical)
        finally:
            try: QApplication.restoreOverrideCursor()
            except: pass

    def populate_double_filter_classes(self, item=None):
        """
        Metodo ad evento eseguito quando l'utente seleziona/deseleziona un piano nella Tab 3.
        Estrae da MSSQL le sole classi IFC presenti nei livelli selezionati, incrociandole
        con PostgreSQL per mostrare SOLO quelle che hanno geometrie reali nell'area scelta.
        """
        selected_storeys = []
        for i in range(self.listWidget_PianoIFC_2.count()):
            it = self.listWidget_PianoIFC_2.item(i)
            if it.checkState() == Qt.Checked:
                selected_storeys.append(it.text())

        self.listWidget_ClasseIFC_2.clear()

        if not selected_storeys:
            placeholder_item = QListWidgetItem(self.tr("Seleziona un piano per caricare le classi relative"))
            placeholder_item.setFlags(Qt.NoItemFlags)
            font = placeholder_item.font()
            font.setItalic(True)
            placeholder_item.setFont(font)
            placeholder_item.setForeground(QColor("gray"))
            self.listWidget_ClasseIFC_2.addItem(placeholder_item)
            return

        if not hasattr(self, '_postgresql_conn_params') or not hasattr(self, '_mssql_conn_params'):
            return

        use_context = self.groupBox_2_FiltroContesto.isChecked()
        current_page_idx = self.stackedWidget.currentIndex() if use_context else -1
        active_ids = set()

        try:
            # --- FASE 1: Recupero ID Geometrici dal Contesto Corrente (PostgreSQL) ---
            conn_pg = self._get_db_connection()
            if conn_pg:
                cur_pg = conn_pg.cursor()
                if use_context:
                    if current_page_idx == 0:  # Filtro predefinito aree
                        selected_table = self.comboBox_SelezionaTipoArea.currentText()
                        selected_areas = self.comboBox_SelezionaArea.checkedItems()
                        if selected_table and selected_areas:
                            areas_formatted = ", ".join([f"'{a.replace('\'', '\'\'')}'" for a in selected_areas])
                            query = f'SELECT g."GlobalId_MSSQL" FROM "ifcgeometry"."entitygeometry" g JOIN "territory"."{selected_table}" t ON ST_Within(g."Geometry", t.geom) WHERE t."name" IN ({areas_formatted}) AND g."GlobalId_MSSQL" IS NOT NULL;'
                            cur_pg.execute(query)
                            active_ids = set(row[0] for row in cur_pg.fetchall())
                    elif current_page_idx == 1:  # Filtro disegno manuale
                        if self.current_area_geometry:
                            wkt_area = self.current_area_geometry.asWkt()
                            srid = self.iface.mapCanvas().mapSettings().destinationCrs().postgisSrid()
                            query = f"SELECT g.\"GlobalId_MSSQL\" FROM \"ifcgeometry\".\"entitygeometry\" g WHERE ST_Intersects(g.\"Geometry\", ST_GeomFromText('{wkt_area}', {srid})) AND g.\"GlobalId_MSSQL\" IS NOT NULL;"
                            cur_pg.execute(query)
                            active_ids = set(row[0] for row in cur_pg.fetchall())
                    elif current_page_idx == 2:  # Filtro lista progetti
                        project_names = []
                        for i in range(self.list_Progetti.count()):
                            it_p = self.list_Progetti.item(i)
                            if it_p.checkState() == Qt.Checked and not it_p.isHidden():
                                project_names.append(it_p.text())
                        if project_names:
                            projects_formatted = ", ".join([f"'{p.replace('\'', '\'\'')}'" for p in project_names])
                            query = f'SELECT g."GlobalId_MSSQL" FROM "ifcgeometry"."entitygeometry" g WHERE g."ProjectName" IN ({projects_formatted}) AND g."GlobalId_MSSQL" IS NOT NULL;'
                            cur_pg.execute(query)
                            active_ids = set(row[0] for row in cur_pg.fetchall())
                cur_pg.close()
                conn_pg.close()

            # --- FASE 2: Estrazione Classi per Piano da MSSQL ---
            QApplication.setOverrideCursor(Qt.WaitCursor)
            host, db, user, pwd = self._mssql_conn_params
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host};DATABASE={db};TrustServerCertificate=yes;"
            if user and str(user).strip(): conn_str += f"UID={user};PWD={pwd};"
            else: conn_str += "Trusted_Connection=yes;"

            conn_ms = pyodbc.connect(conn_str, timeout=15)
            cur_ms = conn_ms.cursor()

            storeys_formatted = ", ".join([f"'{s.replace('\'', '\'\'')}'" for s in selected_storeys])
            query_ms = f"""
                SELECT DISTINCT relListObj.[Value] AS ElementID, elType.ExpressName AS ClasseIFC
                FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId
                JOIN [ifcInstance].[EntityAttributeOfEntityRef] spatialRef ON spatialRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                JOIN [ifcInstance].[Entity] spatialEntity ON spatialEntity.GlobalEntityInstanceId = spatialRef.[Value]
                JOIN [ifcSchema].[Type] spatialType ON spatialEntity.EntityTypeId = spatialType.TypeId
                JOIN [ifcInstance].[Entity] elEntity ON elEntity.GlobalEntityInstanceId = relListObj.[Value]
                JOIN [ifcSchema].[Type] elType ON elEntity.EntityTypeId = elType.TypeId
                JOIN [ifcInstance].[EntityAttributeOfString] storeyName ON storeyName.GlobalEntityInstanceId = spatialRef.[Value] AND storeyName.OrdinalPosition = 3
                WHERE storeyName.[Value] IN ({storeys_formatted})
                  AND spatialType.ExpressName = 'IfcBuildingStorey' -- Evita falsi positivi nel match del nome
                  AND ((relType.ExpressName = 'IfcRelContainedInSpatialStructure' AND spatialRef.OrdinalPosition = 6)
                       OR (relType.ExpressName = 'IfcRelAggregates' AND spatialRef.OrdinalPosition = 5));
            """

            cur_ms.execute(query_ms)
            
            # --- FASE 3: Pulizia Classi senza Corpo Geometrico Reale ---
            classes_set = set()
            for row in cur_ms.fetchall():
                element_id = row[0]
                class_name = row[1]
                if not use_context or (element_id in active_ids):
                    if class_name:
                        classes_set.add(class_name)
            
            cur_ms.close()
            conn_ms.close()

            classes = sorted(list(classes_set))

            # --- FASE 4: Popolamento Widget ---
            if not classes:
                self.listWidget_ClasseIFC_2.addItem(self.tr("Nessuna classe con geometria in questi piani."))
            else:
                for cls in classes:
                    it_cls = QListWidgetItem(str(cls))
                    it_cls.setFlags(it_cls.flags() | Qt.ItemIsUserCheckable)
                    it_cls.setCheckState(Qt.Unchecked)
                    self.listWidget_ClasseIFC_2.addItem(it_cls)

        except Exception as e:
            QgsMessageLog.logMessage(f"Errore caricamento classi filtro doppio: {str(e)}", "ifcSQL", Qgis.Critical)
        finally:
            QApplication.restoreOverrideCursor()





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
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Database non connessi."))
            return

        # 1. Verifica stati dei gruppi (Checkbox)
        use_context = self.groupBox_2_FiltroContesto.isChecked()
        use_ifc = self.groupBox_3_FiltroIFC.isChecked()

        # Se entrambi sono spenti, avvisa l'utente
        if not use_context and not use_ifc:
            QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Seleziona almeno un filtro (Contesto o IFC) o attivali entrambi."))
            return
        
        # --- PREPARAZIONE DATI IFC ---
        ifc_filter_type = self.stackedWidget_IFC.currentIndex() if use_ifc else -1
        selected_classes = []
        selected_storeys = []

        if use_ifc:
            # Caso 0: Filtro Classe attivo
            if ifc_filter_type == 0:
                for index in range(self.listWidget_ClasseIFC.count()):
                    item = self.listWidget_ClasseIFC.item(index)
                    if item.checkState() == Qt.Checked:
                        selected_classes.append(item.text())
                if not selected_classes:
                    QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Filtro IFC attivo: Seleziona almeno una classe dalla lista."))
                    return
            
            # Caso 1: Filtro Piano attivo
            elif ifc_filter_type == 1:
                for index in range(self.listWidget_PianoIFC.count()):
                    item = self.listWidget_PianoIFC.item(index)
                    if item.checkState() == Qt.Checked:
                        selected_storeys.append(item.text())
                if not selected_storeys:
                    QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Filtro Piano attivo: Seleziona almeno un piano dalla lista."))
                    return

            # Caso 2: Filtro Doppio attivo (PAGINA 3)
            elif ifc_filter_type == 2:
                for index in range(self.listWidget_PianoIFC_2.count()):
                    item = self.listWidget_PianoIFC_2.item(index)
                    if item.checkState() == Qt.Checked:
                        selected_storeys.append(item.text())
                for index in range(self.listWidget_ClasseIFC_2.count()):
                    item = self.listWidget_ClasseIFC_2.item(index)
                    if item.flags() & Qt.ItemIsUserCheckable and item.checkState() == Qt.Checked:
                        selected_classes.append(item.text())
                if not selected_storeys or not selected_classes:
                    QMessageBox.warning(self, self.tr("Attenzione"), self.tr("Filtro Doppio attivo: Spunta almeno un piano e una classe relazionata."))
                    return

        # Se viene usato il filtro piano (1) o il filtro doppio (2), estraiamo da MSSQL gli ID degli elementi relazionati
        storey_element_ids = []
        if use_ifc and ifc_filter_type in [1, 2]:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                host, db, user, pwd = self._mssql_conn_params
                conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host};DATABASE={db};TrustServerCertificate=yes;"
                if user and str(user).strip(): conn_str += f"UID={user};PWD={pwd};"
                else: conn_str += "Trusted_Connection=yes;"
                
                conn_ms = pyodbc.connect(conn_str, timeout=15)
                cur_ms = conn_ms.cursor()
                
                storeys_formatted = ", ".join([f"'{s.replace('\'', '\'\'')}'" for s in selected_storeys])
                
                if ifc_filter_type == 1:
                    # Query standard per piano (tutti gli elementi del piano)
                    query_ms = f"""
                        SELECT DISTINCT relListObj.[Value]
                        FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                        JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] spatialRef ON spatialRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcInstance].[Entity] spatialEntity ON spatialEntity.GlobalEntityInstanceId = spatialRef.[Value]
                        JOIN [ifcSchema].[Type] spatialType ON spatialEntity.EntityTypeId = spatialType.TypeId
                        JOIN [ifcInstance].[EntityAttributeOfString] storeyName ON storeyName.GlobalEntityInstanceId = spatialRef.[Value] AND storeyName.OrdinalPosition = 3
                        WHERE storeyName.[Value] IN ({storeys_formatted})
                          AND spatialType.ExpressName = 'IfcBuildingStorey'
                          AND ((relType.ExpressName = 'IfcRelContainedInSpatialStructure' && spatialRef.OrdinalPosition = 6)
                               OR (relType.ExpressName = 'IfcRelAggregates' && spatialRef.OrdinalPosition = 5));
                    """
                else:
                    # Query per filtro doppio (estrazione mirata per piano E classe dell'elemento)
                    classes_formatted = ", ".join([f"'{c.replace('\'', '\'\'')}'" for c in selected_classes])
                    query_ms = f"""
                        SELECT DISTINCT relListObj.[Value]
                        FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                        JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] spatialRef ON spatialRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcInstance].[Entity] spatialEntity ON spatialEntity.GlobalEntityInstanceId = spatialRef.[Value]
                        JOIN [ifcSchema].[Type] spatialType ON spatialEntity.EntityTypeId = spatialType.TypeId
                        JOIN [ifcInstance].[Entity] elEntity ON elEntity.GlobalEntityInstanceId = relListObj.[Value]
                        JOIN [ifcSchema].[Type] elType ON elEntity.EntityTypeId = elType.TypeId
                        JOIN [ifcInstance].[EntityAttributeOfString] storeyName ON storeyName.GlobalEntityInstanceId = spatialRef.[Value] AND storeyName.OrdinalPosition = 3
                        WHERE storeyName.[Value] IN ({storeys_formatted})
                          AND spatialType.ExpressName = 'IfcBuildingStorey'
                          AND elType.ExpressName IN ({classes_formatted})
                          AND ((relType.ExpressName = 'IfcRelContainedInSpatialStructure' AND spatialRef.OrdinalPosition = 6)
                               OR (relType.ExpressName = 'IfcRelAggregates' AND spatialRef.OrdinalPosition = 5));
                    """
                cur_ms.execute(query_ms)
                storey_element_ids = [row[0] for row in cur_ms.fetchall() if row[0]]
                cur_ms.close()
                conn_ms.close()
                
                if not storey_element_ids:
                    QMessageBox.warning(self, self.tr("Nessun Risultato"), self.tr("Nessun elemento geometrico corrisponde ai criteri del filtro combinato."))
                    return
            except Exception as e:
                QMessageBox.critical(self, self.tr("Errore Relazione Piani"), f"Errore durante l'estrazione degli elementi: {str(e)}")
                return
            finally:
                QApplication.restoreOverrideCursor()

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
            if ifc_filter_type == 0:  # Tab delle sole classi
                classes_sql = ", ".join([f"'{c}'" for c in selected_classes])
                where_conditions.append(f'g."IfcClass" IN ({classes_sql})')
            elif ifc_filter_type in [1, 2]:  # Tab dei piani o filtro doppio (entrambi veicolati tramite ID numerici estratti a priori)
                ids_sql = ", ".join([str(x) for x in storey_element_ids])
                where_conditions.append(f'g."GlobalId_MSSQL" IN ({ids_sql})')

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

        # 5. Configurazione Layer QGIS
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

        # 2. Parte IFC (Classi o Piani)
        if use_ifc: 
            if ifc_filter_type == 0:
                if len(selected_classes) <= 3:
                    layer_parts.append(self.tr("Classi ({classes})").format(classes=", ".join(selected_classes)))
                else:
                    layer_parts.append(self.tr("Classi IFC"))
            elif ifc_filter_type == 1:
                if len(selected_storeys) <= 3:
                    layer_parts.append(self.tr("Piani ({storeys})").format(storeys=", ".join(selected_storeys)))
                else:
                    layer_parts.append(self.tr("Piani IFC"))
            elif ifc_filter_type == 2:
                layer_parts.append(self.tr("Classi+Piani"))

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
        self.listWidget_PianoIFC.clear()
        self.lineEdit_PianoIFC.clear()

        self.listWidget_PianoIFC_2.clear()
        self.lineEdit_PianoIFC_2.clear()
        self.listWidget_ClasseIFC_2.clear()
        self.lineEdit_ClasseIFC_2.clear()

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

    # Funzione di filtro visivo per la lista dei piani IFC
    def filter_storey_list(self, text):
        """Filtra visivamente gli elementi della lista piani in base al testo digitato."""
        for i in range(self.listWidget_PianoIFC.count()):
            item = self.listWidget_PianoIFC.item(i)
            if text.lower() in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)
    def filter_storey_list_2(self, text):
        """Filtra visivamente gli elementi della lista piani nella Tab 3."""
        for i in range(self.listWidget_PianoIFC_2.count()):
            item = self.listWidget_PianoIFC_2.item(i)
            if text.lower() in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)
    def filter_class_list_2(self, text):
        """Filtra visivamente gli elementi della lista classi nella Tab 3."""
        for i in range(self.listWidget_ClasseIFC_2.count()):
            item = self.listWidget_ClasseIFC_2.item(i)
            # Controlla che sia un elemento selezionabile e non il testo segnaposto grigio
            if item.flags() & Qt.ItemIsUserCheckable:
                if text.lower() in item.text().lower():
                    item.setHidden(False)
                else:
                    item.setHidden(True)



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





































#     ██████  ██    ██ ███████ ██████  ██    ██      ██████ ██       █████  ███████ ███████ 
#    ██    ██ ██    ██ ██      ██   ██  ██  ██      ██      ██      ██   ██ ██      ██      
#    ██    ██ ██    ██ █████   ██████    ████       ██      ██      ███████ ███████ ███████ 
#    ██ ▄▄ ██ ██    ██ ██      ██   ██    ██        ██      ██      ██   ██      ██      ██ 
#     ██████   ██████  ███████ ██   ██    ██         ██████ ███████ ██   ██ ███████ ███████ 
#        ▀▀                                                                                 
#                                                                                           



 

class IFCPropertiesDialog(Ui_QueryProperties, QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.current_layer = None

        # Inizializza il LED grigio statale
        self.set_led_color("gray")
        self.label_led_2.setText(self.tr("Seleziona e connetti"))
        self.treeWidget.setHeaderLabels([self.tr("Proprietà"), self.tr("Valore"), self.tr("Unità")])

        # Collega l'evento di cambio selezione della ComboBox
        self.comboBox_MSSQL.currentIndexChanged.connect(self.reset_ui_on_connection_change_MSSQL)
        self.comboBox_PostgreSQL.currentIndexChanged.connect(self.reset_ui_on_connection_change_PostgreSQL)
        
        # Collega i pulsanti alle funzioni di creazione nuova connessione
        self.pushButton_NuovaConnessioneMSSQL.clicked.connect(self.create_new_connection_MSSQL)
        self.pushButton_NuovaConnessionePostgreSQL.clicked.connect(self.create_new_connection_PostgreSQL)
        
        # Connetti entrambi i database contemporaneamente
        self.pushButton_ConnettiDB_2.clicked.connect(self.connect_both_databases)

        self.pushButton_SelezionaElemento.clicked.connect(self.activate_selection_tool)
        self.button_ResetFiltri.clicked.connect(self.reset_properties_ui)

        # Logica per ricerca testuale sulle proprietà in tempo reale
        self.lineEdit_CercaProprieta.textChanged.connect(self.filter_properties_tree)



    def set_led_color(self, color_name):
        palette = self.label_led_2.palette()
        palette.setColor(self.label_led_2.backgroundRole(), QColor(color_name))
        self.label_led_2.setAutoFillBackground(True)
        self.label_led_2.setPalette(palette)
        self.label_led_2.show()

    def reset_ui_on_connection_change_MSSQL(self):
        """Resetta il LED e l'etichetta quando la selezione della connessione MSSQL cambia."""
        self.set_led_color("gray")
        self.label_led_2.setText(self.tr("Seleziona e connetti"))
        if hasattr(self, '_mssql_conn_params'):
            del self._mssql_conn_params

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
        """Resetta il LED e l'etichetta quando la selezione della connessione PostgreSQL cambia."""
        self.set_led_color("gray")
        self.label_led_2.setText(self.tr("Seleziona e connetti"))
        if hasattr(self, '_postgresql_conn_params'):
            del self._postgresql_conn_params
        
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

    def populate_connection_combo_MSSQL(self):
        self.comboBox_MSSQL.clear()
        settings = QSettings() 
        settings.beginGroup('MSSQL/connections')
        connections = settings.childGroups()
        self.comboBox_MSSQL.addItems(connections)

    def populate_connection_combo_PostgreSQL(self):
        self.comboBox_PostgreSQL.clear()
        settings = QSettings()
        settings.beginGroup('PostgreSQL/connections')
        connections = settings.childGroups()
        self.comboBox_PostgreSQL.addItems(connections)

    def create_new_connection_MSSQL(self): 
        self.iface.openDataSourceManagerPage("mssql")    
        self.close()

    def create_new_connection_PostgreSQL(self): 
        self.iface.openDataSourceManagerPage("postgres")    
        self.close()
    
    def verify_database_alignment(self):
        """Verifica l'allineamento confrontando i GUID dei due database target."""
        guid_direct_mssql = None
        try:
            host, db, user, pwd = self._mssql_conn_params
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host};DATABASE={db};TrustServerCertificate=yes;"
            if user and str(user).strip():
                conn_str += f"UID={user};PWD={pwd};"
            else:
                conn_str += "Trusted_Connection=yes;"

            conn = pyodbc.connect(conn_str, timeout=15)
            cursor = conn.cursor()
            query_guid = "SELECT service_broker_guid FROM sys.databases WHERE name = 'ifcSQL'"
            cursor.execute(query_guid)
            row = cursor.fetchone()
            if row:
                guid_direct_mssql = str(row[0])
            conn.close()

            if not guid_direct_mssql:
                return False, self.tr("Impossibile recuperare GUID dal DB MSSQL (ifcSQL).")
        except Exception as e:
            return False, self.tr("Errore lettura GUID MSSQL Diretto: {error}").format(error=str(e))

        guid_via_postgres = None
        try:
            h_pg, db_pg, u_pg, p_pg, port_pg = self._postgresql_conn_params
            conn_pg = psycopg2.connect(host=h_pg, database=db_pg, user=u_pg, password=p_pg, port=port_pg)
            cursor_pg = conn_pg.cursor()
            query_check = "SELECT db_guid FROM public.mssql_identity_card"
            cursor_pg.execute(query_check)
            row_pg = cursor_pg.fetchone()
            conn_pg.close()

            if row_pg and row_pg[0]:
                guid_via_postgres = str(row_pg[0])
            else:
                return False, self.tr("La tabella 'public.mssql_identity_card' in Postgres è vuota o non accessibile.")
        except Exception as e:
            return False, self.tr("Errore leggendo 'mssql_identity_card' da Postgres:\n\n{error}").format(error=str(e))

        if guid_direct_mssql.strip().lower() == guid_via_postgres.strip().lower():
            return True, self.tr("OK")
        else:
            return False, (self.tr("DISALLINEAMENTO DATABASE!\n\n1. GUID MSSQL (QGIS): {guid_ms}\n2. GUID MSSQL (visto da PG): {guid_pg}\n\nPostgreSQL è collegato a un database MSSQL diverso da quello selezionato.").format(guid_ms=guid_direct_mssql, guid_pg=guid_via_postgres))

    def connect_both_databases(self):
        self.mssql_ready = False
        self.postgres_ready = False
        self.connection_errors = []

        self.set_led_color("#ffd700") # Giallo/Oro
        self.label_led_2.setText(self.tr("Connessione..."))
        self.pushButton_ConnettiDB_2.setEnabled(False)

        self.connect_selected_DB_MSSQL()
        self.connect_selected_DB_PostgreSQL()

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

    def check_if_both_ready(self):
        mssql_finished = self.mssql_ready or any("MSSQL" in e for e in self.connection_errors)
        pg_finished = self.postgres_ready or any("PostgreSQL" in e for e in self.connection_errors)

        if not (mssql_finished and pg_finished):
            return

        if self.connection_errors:
            self.set_led_color("#fa3e3e")
            self.label_led_2.setText(self.tr("Errore Connessione"))
            self.pushButton_ConnettiDB_2.setEnabled(True)
            QMessageBox.critical(self, self.tr("Errore di Connessione"), "\n\n".join(self.connection_errors))
            return

        try:
            is_aligned, error_message = self.verify_database_alignment()
            if is_aligned:
                self.set_led_color("#90ee90") # Verde
                self.label_led_2.setText(self.tr("Connessi e Allineati"))
            else:
                self.set_led_color("#fa3e3e")
                self.label_led_2.setText(self.tr("Disallineati!"))
                QMessageBox.critical(self, self.tr("Disallineamento Database"), error_message)
                if hasattr(self, '_mssql_conn_params'): del self._mssql_conn_params
                if hasattr(self, '_postgresql_conn_params'): del self._postgresql_conn_params
        except Exception as e:
            self.set_led_color("#fa3e3e")
            self.label_led_2.setText(self.tr("Errore Script"))
            QMessageBox.critical(self, self.tr("Errore"), str(e))
        finally:
            self.pushButton_ConnettiDB_2.setEnabled(True)

    







    # =========================================================================
    # STRUMENTO DI SELEZIONE SULLA MAPPA E ESECUZIONE DELLE QUERY
    # =========================================================================

    def activate_selection_tool(self):
        """Attiva lo strumento di selezione geometrica sul canvas di QGIS."""
        if not hasattr(self, '_mssql_conn_params'):
            QMessageBox.warning(self, self.tr("Database non connesso"), 
            self.tr("Prima di interrogare la mappa devi connettere i database."))
            return
        
        canvas = self.iface.mapCanvas()
        self.map_tool = IFCSelectionTool(canvas, self)
        canvas.setMapTool(self.map_tool)
    
        
        self.iface.mainWindow().statusBar().showMessage(self.tr("Strumento di interrogazione IFC attivo: Clicca su un elemento nella mappa."))


    def reset_properties_ui(self):
        self.lineEdit_CercaProprieta.clear()
        self.treeWidget.clear()

        # PULIZIA GLOBALE: Rimuove la selezione da TUTTI i layer del progetto
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                try:
                    lyr.removeSelection()
                except RuntimeError:
                    # Gestisce il caso in cui un layer sia stato rimosso ma sia ancora in memoria
                    pass

        # Resetta il riferimento al layer corrente
        self.current_layer = None


    def closeEvent(self, event):
        # Svuota l'albero, pulisce la ricerca e deseleziona l'oggetto dalla mappa
        self.reset_properties_ui()
        
        # Consente a Qt di procedere con la chiusura standard del widget
        super().closeEvent(event)
    
    
    def filter_properties_tree(self, text):
        text = text.lower()
        for i in range(self.treeWidget.topLevelItemCount()):
            top_item = self.treeWidget.topLevelItem(i)
            top_item_visible = False
            for j in range(top_item.childCount()):
                child = top_item.child(j)
                child_visible = False
                if child.childCount() > 0:
                    for k in range(child.childCount()):
                        sub_child = child.child(k)
                        if text in sub_child.text(1).lower() or text in sub_child.text(2).lower():
                            sub_child.setHidden(False); child_visible = True
                        else: sub_child.setHidden(True)
                else:
                    if text in child.text(0).lower() or text in child.text(1).lower() or text in child.text(2).lower():
                        child_visible = True
                
                if child_visible: child.setHidden(False); top_item_visible = True
                else: child.setHidden(True)
            
            if top_item_visible or text in top_item.text(0).lower():
                top_item.setHidden(False)
                if text: top_item.setExpanded(True)
            else: top_item.setHidden(True)

        
    def execute_report_query(self, target_id, layer=None):
        """Esegue l'intero blocco di query atomiche e popola l'albero delle proprietà."""
        # --- GUARDIA ANTI CLICK SECONDO ELEMENTO
        if getattr(self, "_query_in_corso", False):
            return
        self._query_in_corso = True
        
        self.current_layer = layer

        # --- CRONOMETRO INIZIALE ---
        t_inizio = time.time()

        host, db, user, pwd = self._mssql_conn_params
        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host};DATABASE={db};TrustServerCertificate=yes;"
        
        if user and str(user).strip():
            conn_str += f"UID={user};PWD={pwd};"
        else:
            conn_str += "Trusted_Connection=yes;"
            
        try:
            conn = pyodbc.connect(conn_str, timeout=15)
            cursor_main = conn.cursor()
            cursor_value = conn.cursor()
            
            # =================================================================================
            # FASE 0: VERIFICA E CORREZIONE DELL'ID
            # =================================================================================
            t_fase0 = time.time()
            
            check_query = """
                SELECT [Value] FROM [ifcInstance].[EntityAttributeOfString]
                WHERE GlobalEntityInstanceId = ? AND OrdinalPosition = 1 AND LEN(ISNULL([Value], '')) = 22;
            """
            cursor_main.execute(check_query, target_id)
            if not cursor_main.fetchone():
                correct_id_query = """
                    WITH DiagnosticaIniziale AS (
                        SELECT attr1.GlobalEntityInstanceId AS WrongEntityId, attr3.[Value] AS TrueIfcGlobalId
                        FROM [ifcInstance].[EntityAttributeOfString] attr1
                        JOIN [ifcInstance].[EntityAttributeOfString] attr3 ON attr1.GlobalEntityInstanceId = attr3.GlobalEntityInstanceId
                        WHERE attr1.GlobalEntityInstanceId = ? AND attr1.OrdinalPosition = 1 AND LEN(ISNULL(attr1.[Value], '')) <> 22
                            AND attr3.OrdinalPosition = 3 AND LEN(ISNULL(attr3.[Value], '')) = 22
                    ),
                    MappaProgetto AS (
                        SELECT d.WrongEntityId, d.TrueIfcGlobalId, assign.ProjectId
                        FROM DiagnosticaIniziale d
                        INNER JOIN [ifcProject].[EntityInstanceIdAssignment] assign ON d.WrongEntityId = assign.GlobalEntityInstanceId
                    ),
                    RicercaEntitaCorretta AS (
                        SELECT attr_final.GlobalEntityInstanceId AS CorrectEntityId
                        FROM MappaProgetto p
                        INNER JOIN [ifcProject].[EntityInstanceIdAssignment] project_all ON p.ProjectId = project_all.ProjectId
                        INNER JOIN [ifcInstance].[EntityAttributeOfString] attr_final ON project_all.GlobalEntityInstanceId = attr_final.GlobalEntityInstanceId
                        WHERE attr_final.OrdinalPosition = 1 AND attr_final.[Value] = p.TrueIfcGlobalId
                    )
                    SELECT CorrectEntityId FROM RicercaEntitaCorretta;
                """
                cursor_main.execute(correct_id_query, target_id)
                row_corr = cursor_main.fetchone()
                if row_corr:
                    target_id = str(row_corr[0])
                else:
                    QMessageBox.critical(self, self.tr("Errore diagnostica"), f"L'ID {target_id} non corrisponde a nessuna entità IFC valida.")
                    return

            # Pulisce l'albero prima di caricarne uno nuovo
            self.treeWidget.clear()

            QgsMessageLog.logMessage(f"FASE 0 (Diagnostica) impiega: {time.time() - t_fase0:.3f} secondi", "IFC_Filtro", Qgis.Info)


            # =================================================================================
            # ESTRAZIONE DIZIONARIO UNITÀ TEMPORANEO DALL'OGGETTO CLICCATO
            # =================================================================================
            
            t_unita = time.time()
            
            project_id_mssql = None
            if layer:
                selected_features = layer.selectedFeatures()
                if selected_features:
                    feat = selected_features[0]
                    idx_pid = layer.fields().indexOf("ProjectNumber_MSSQL")
                    if idx_pid != -1 and feat.attribute("ProjectNumber_MSSQL") != NULL:
                        project_id_mssql = feat.attribute("ProjectNumber_MSSQL")
            
            if project_id_mssql is None:
                cursor_main.execute("SELECT ProjectId FROM [ifcProject].[EntityInstanceIdAssignment] WHERE GlobalEntityInstanceId = ?", target_id)
                row_pid = cursor_main.fetchone()
                if row_pid:
                    project_id_mssql = row_pid[0]

            SI_PREFIXES = {"EXA": "E", "PETA": "P", "TERA": "T", "GIGA": "G", "MEGA": "M", "KILO": "k", "HECTO": "h", "DECA": "da", "DECI": "d", "CENTI": "c", "MILLI": "m", "MICRO": "μ", "NANO": "n", "PICO": "p", "FEMTO": "f", "ATTO": "a"}
            SI_UNITS = {"AMPERE": "A", "BECQUEREL": "Bq", "CANDELA": "cd", "COULOMB": "C", "CUBIC_METRE": "m³", "DEGREE_CELSIUS": "°C", "FARAD": "F", "GRAM": "g", "GRAY": "Gy", "HENRY": "H", "HERTZ": "Hz", "JOULE": "J", "KELVIN": "K", "LUMEN": "lm", "LUX": "lx", "METRE": "m", "MOLE": "mol", "NEWTON": "N", "OHM": "Ω", "PASCAL": "Pa", "RADIAN": "rad", "SECOND": "s", "SIEMENS": "S", "SIEVERT": "Sv", "SQUARE_METRE": "m²", "STERADIAN": "sr", "TESLA": "T", "VOLT": "V", "WATT": "W", "WEBER": "Wb"}
            CONVERSION_UNITS = {"INCH": "in", "FOOT": "ft", "US SURVEY FOOT": "ft_us", "YARD": "yd", "MILE": "mi", "SQUARE INCH": "in²", "SQUARE FOOT": "ft²", "SQUARE YARD": "yd²", "ACRE": "ac", "SQUARE MILE": "mi²", "CUBIC INCH": "in³", "CUBIC FOOT": "ft³", "CUBIC YARD": "yd³", "LITRE": "L", "LITER": "L", "FLUID OUNCE UK": "fl oz (UK)", "FLUID OUNCE US": "fl oz (US)", "PINT UK": "pt (UK)", "PINT US": "pt (US)", "GALLON UK": "gal (UK)", "GALLON US": "gal (US)", "DEGREE": "°", "OUNCE": "oz", "POUND": "lb", "TON UK": "ton (UK)", "TON US": "ton (US)", "LBF": "lbf", "KIP": "kip", "PSI": "psi", "KSI": "ksi", "MINUTE": "min", "HOUR": "h", "DAY": "d", "BTU": "Btu"}

            def format_exponent_abbr(exponent):
                if exponent == 1: return ""
                superscripts = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
                return "".join(superscripts.get(c, c) for c in str(exponent))

            project_units_map = {}
            if project_id_mssql:
                query_si_conversion = """
                    WITH TargetProject AS (
                        SELECT TOP 1 assignment.GlobalEntityInstanceId FROM [ifcProject].[EntityInstanceIdAssignment] assignment
                        JOIN [ifcInstance].[Entity] eProject ON assignment.GlobalEntityInstanceId = eProject.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] tProject ON eProject.EntityTypeId = tProject.TypeId AND tProject.ExpressName = 'IfcProject'
                        WHERE assignment.[ProjectId] = ?
                    ),
                    ProjectUnits AS (
                        SELECT unitRef.Value AS UnitGID FROM TargetProject tp
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] unitsListRef ON unitsListRef.GlobalEntityInstanceId = tp.GlobalEntityInstanceId AND unitsListRef.OrdinalPosition = 9
                        JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] unitRef ON unitRef.GlobalEntityInstanceId = unitsListRef.Value
                    )
                    SELECT 'IfcSIUnit' AS ExpressName, enumUnitType.EnumItemName AS UnitType, enumPrefix.EnumItemName AS Prefix, enumName.EnumItemName AS UnitName FROM ProjectUnits pu
                    JOIN [ifcInstance].[Entity] eUnit ON pu.UnitGID = eUnit.GlobalEntityInstanceId
                    JOIN [ifcSchema].[Type] tUnit ON eUnit.EntityTypeId = tUnit.TypeId AND tUnit.ExpressName = 'IfcSIUnit'
                    JOIN [ifcInstance].[EntityAttributeOfEnum] attrUnitType ON attrUnitType.GlobalEntityInstanceId = pu.UnitGID AND attrUnitType.OrdinalPosition = 2
                    JOIN [ifcSchema].[EnumItem] enumUnitType ON enumUnitType.TypeId = attrUnitType.TypeId AND enumUnitType.EnumItemId = attrUnitType.Value
                    LEFT JOIN [ifcInstance].[EntityAttributeOfEnum] attrPrefix ON attrPrefix.GlobalEntityInstanceId = pu.UnitGID AND attrPrefix.OrdinalPosition = 3
                    LEFT JOIN [ifcSchema].[EnumItem] enumPrefix ON enumPrefix.TypeId = attrPrefix.TypeId AND enumPrefix.EnumItemId = attrPrefix.Value
                    JOIN [ifcInstance].[EntityAttributeOfEnum] attrName ON attrName.GlobalEntityInstanceId = pu.UnitGID AND attrName.OrdinalPosition = 4
                    JOIN [ifcSchema].[EnumItem] enumName ON enumName.TypeId = attrName.TypeId AND enumName.EnumItemId = attrName.Value
                    UNION ALL
                    SELECT 'IfcConversionBasedUnit' AS ExpressName, enumUnitType.EnumItemName AS UnitType, NULL AS Prefix, attrNameString.Value AS UnitName FROM ProjectUnits pu
                    JOIN [ifcInstance].[Entity] eUnit ON pu.UnitGID = eUnit.GlobalEntityInstanceId
                    JOIN [ifcSchema].[Type] tUnit ON eUnit.EntityTypeId = tUnit.TypeId AND tUnit.ExpressName = 'IfcConversionBasedUnit'
                    JOIN [ifcInstance].[EntityAttributeOfEnum] attrUnitType ON attrUnitType.GlobalEntityInstanceId = pu.UnitGID AND attrUnitType.OrdinalPosition = 2
                    JOIN [ifcSchema].[EnumItem] enumUnitType ON enumUnitType.TypeId = attrUnitType.TypeId AND enumUnitType.EnumItemId = attrUnitType.Value
                    JOIN [ifcInstance].[EntityAttributeOfString] attrNameString ON attrNameString.GlobalEntityInstanceId = pu.UnitGID AND attrNameString.OrdinalPosition = 3
                """
                cursor_main.execute(query_si_conversion, project_id_mssql)
                for riga in cursor_main.fetchall():
                    exp_n, u_type, p_raw, u_name = riga
                    if exp_n == 'IfcConversionBasedUnit':
                        abbr = CONVERSION_UNITS.get(u_name.upper(), u_name)
                    else:
                        abbr_p = SI_PREFIXES.get(p_raw, "") if p_raw else ""
                        abbr_u = SI_UNITS.get(u_name.upper(), u_name)
                        abbr = abbr_p + abbr_u
                    if u_type: project_units_map[u_type.upper()] = abbr

                query_derived = """
                    WITH TargetProject AS (
                        SELECT TOP 1 assignment.GlobalEntityInstanceId FROM [ifcProject].[EntityInstanceIdAssignment] assignment
                        JOIN [ifcInstance].[Entity] eProject ON assignment.GlobalEntityInstanceId = eProject.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] tProject ON eProject.EntityTypeId = tProject.TypeId AND tProject.ExpressName = 'IfcProject'
                        WHERE assignment.[ProjectId] = ?
                    ),
                    ProjectUnits AS (
                        SELECT unitRef.Value AS UnitGID FROM TargetProject tp
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] unitsListRef ON unitsListRef.GlobalEntityInstanceId = tp.GlobalEntityInstanceId AND unitsListRef.OrdinalPosition = 9
                        JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] unitRef ON unitRef.GlobalEntityInstanceId = unitsListRef.Value
                    ),
                    DerivedUnits AS (
                        SELECT pu.UnitGID AS DerivedUnitGID, enumUnitType.EnumItemName AS UnitType FROM ProjectUnits pu
                        JOIN [ifcInstance].[Entity] eUnit ON pu.UnitGID = eUnit.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] tUnit ON eUnit.EntityTypeId = tUnit.TypeId AND tUnit.ExpressName = 'IfcDerivedUnit'
                        JOIN [ifcInstance].[EntityAttributeOfEnum] attrUnitType ON attrUnitType.GlobalEntityInstanceId = pu.UnitGID AND attrUnitType.OrdinalPosition = 2
                        JOIN [ifcSchema].[EnumItem] enumUnitType ON enumUnitType.TypeId = attrUnitType.TypeId AND enumUnitType.EnumItemId = attrUnitType.Value
                    ),
                    DerivedElements AS (
                        SELECT du.DerivedUnitGID, du.UnitType, elemRef.Value AS ElementGID FROM DerivedUnits du
                        JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] elemRef ON elemRef.GlobalEntityInstanceId = du.DerivedUnitGID
                    )
                    SELECT de.DerivedUnitGID, de.UnitType, attrExp.Value AS Exponent, tBase.ExpressName AS BaseUnitExpressName, enumPrefix.EnumItemName AS SIPrefix, enumName.EnumItemName AS SIUnitName, attrNameString.Value AS ConversionUnitName FROM DerivedElements de
                    JOIN [ifcInstance].[EntityAttributeOfInteger] attrExp ON attrExp.GlobalEntityInstanceId = de.ElementGID AND attrExp.OrdinalPosition = 2
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] attrBaseUnit ON attrBaseUnit.GlobalEntityInstanceId = de.ElementGID AND attrBaseUnit.OrdinalPosition = 1
                    JOIN [ifcInstance].[Entity] eBase ON attrBaseUnit.Value = eBase.GlobalEntityInstanceId
                    JOIN [ifcSchema].[Type] tBase ON eBase.EntityTypeId = tBase.TypeId
                    LEFT JOIN [ifcInstance].[EntityAttributeOfEnum] attrPrefix ON attrPrefix.GlobalEntityInstanceId = attrBaseUnit.Value AND attrPrefix.OrdinalPosition = 3
                    LEFT JOIN [ifcSchema].[EnumItem] enumPrefix ON enumPrefix.TypeId = attrPrefix.TypeId AND enumPrefix.EnumItemId = attrPrefix.Value
                    LEFT JOIN [ifcInstance].[EntityAttributeOfEnum] attrName ON attrName.GlobalEntityInstanceId = attrBaseUnit.Value AND attrName.OrdinalPosition = 4
                    LEFT JOIN [ifcSchema].[EnumItem] enumName ON enumName.TypeId = attrName.TypeId AND enumName.EnumItemId = attrName.Value
                    LEFT JOIN [ifcInstance].[EntityAttributeOfString] attrNameString ON attrNameString.GlobalEntityInstanceId = attrBaseUnit.Value AND attrNameString.OrdinalPosition = 3
                """
                cursor_main.execute(query_derived, project_id_mssql)
                diz_derivate = {}
                for riga in cursor_main.fetchall():
                    d_gid, u_type, exp, b_type, si_pref, si_n, conv_n = riga
                    si_n = si_n if si_n else ""
                    conv_n = conv_n if conv_n else ""
                    if b_type == 'IfcSIUnit':
                        abbr_pezzo = SI_PREFIXES.get(si_pref, "") + SI_UNITS.get(si_n.upper(), si_n)
                    else:
                        abbr_pezzo = CONVERSION_UNITS.get(conv_n.upper(), conv_n)
                    if d_gid not in diz_derivate:
                        diz_derivate[d_gid] = {'UnitType': u_type, 'Positivi': [], 'Negativi': []}
                    if exp > 0: diz_derivate[d_gid]['Positivi'].append(f"{abbr_pezzo}{format_exponent_abbr(exp)}")
                    elif exp < 0: diz_derivate[d_gid]['Negativi'].append(f"{abbr_pezzo}{format_exponent_abbr(abs(exp))}")
                
                for gid, info in diz_derivate.items():
                    pos = "·".join(info['Positivi'])
                    neg = "·".join(info['Negativi'])                    
                    # Se ci sono più unità al denominatore (es. m² e K), le racchiudiamo 
                    # tra parentesi per evitare qualsiasi ambiguità matematica
                    denom = f"({neg})" if len(info['Negativi']) > 1 else neg
                    
                    if denom:
                        abbr_completa = f"{pos}/{denom}" if pos else f"1/{denom}"
                    else:
                        abbr_completa = pos
                        
                    if info['UnitType']: project_units_map[info['UnitType'].upper()] = abbr_completa

            def find_unit_abbr(express_name, units_map):
                if not express_name or not units_map: return ""
                name = express_name.upper()

                # Solo le eccezioni dove la regola IFCxxxMEASURE -> xxxUNIT non vale.
                exceptions = {
                    'IFCDURATION': 'TIMEUNIT',
                    'IFCPOSITIVELENGTHMEASURE': 'LENGTHUNIT',
                    'IFCNONNEGATIVELENGTHMEASURE': 'LENGTHUNIT',
                    'IFCPOSITIVEPLANEANGLEMEASURE': 'PLANEANGLEUNIT',
                    'IFCSECTIONALAREAINTEGRALMEASURE': 'SECTIONAREAINTEGRALUNIT',  
                    'IFCTHERMALCONDUCTIVITYMEASURE': 'THERMALCONDUCTANCEUNIT',     
                }

                target_type = exceptions.get(name)
                if target_type is None:
                    # Regola generale: IFCxxxMEASURE -> xxxUNIT
                    base = name[3:] if name.startswith('IFC') else name
                    if base.endswith('MEASURE'):
                        base = base[:-len('MEASURE')]
                    target_type = base + 'UNIT'

                return units_map.get(target_type, "")

            QgsMessageLog.logMessage(f"FASE UNITÀ impiega: {time.time() - t_unita:.3f} secondi", "IFC_Filtro", Qgis.Info)

            # =================================================================================
            # CLASSE E PROGETTO (Recuperati direttamente dal Layer di QGIS)
            # =================================================================================
            project_name = self.tr("Non definito")
            ifc_class = self.tr("Non definito")
            
            if layer:
                # Recupera la feature appena selezionata dallo strumento sulla mappa
                selected_features = layer.selectedFeatures()
                if selected_features:
                    feat = selected_features[0]
                    
                    # Estrae i valori controllando che i campi esistano nel layer
                    idx_proj = layer.fields().indexOf("ProjectName")
                    idx_class = layer.fields().indexOf("IfcClass")
                    
                    if idx_proj != -1 and feat.attribute("ProjectName") != NULL:
                        project_name = str(feat.attribute("ProjectName"))
                    if idx_class != -1 and feat.attribute("IfcClass") != NULL:
                        ifc_class = str(feat.attribute("IfcClass"))
            
            # Crea il nodo principale in cima a tutti
            class_proj_root = QTreeWidgetItem(self.treeWidget, [self.tr("CLASSE E PROGETTO"), "", ""])
            QTreeWidgetItem(class_proj_root, [self.tr("IFC Class"), ifc_class, ""])
            QTreeWidgetItem(class_proj_root, [self.tr("Project"), project_name, ""])
            


            # =================================================================================
            # FASE 1: ATTRIBUTI STANDARD E PREDEFINED TYPE
            # =================================================================================
            
            t_attributi = time.time()
            
            attr_root = QTreeWidgetItem(self.treeWidget, [self.tr("ATTRIBUTES"), "", ""])

            if ifc_class == "IfcSpace":
                # --- PIPELINE PARALLELA: IFCSPACE ---
                query_string = """
                    SELECT OrdinalPosition, Value FROM [ifcInstance].[EntityAttributeOfString]
                    WHERE GlobalEntityInstanceId = ? ORDER BY OrdinalPosition;
                """
                cursor_main.execute(query_string, target_id)
                risultati_string = cursor_main.fetchall()
                
                # Mappatura specifica per IfcSpace (Posizione 8 diventa LongName)
                mappatura_string = {1: "GlobalId", 3: "Name", 5: "ObjectType", 8: "LongName"}
                
                if risultati_string:
                    for row in risultati_string:
                        nome = mappatura_string.get(row[0], f"Altro (Posizione {row[0]})")
                        QTreeWidgetItem(attr_root, [nome, str(row[1]), ""])

                # Query Enum per CompositionType (OrdinalPosition = 9)
                query_enum_9 = """
                    SELECT ei.EnumItemName FROM [ifcInstance].[EntityAttributeOfEnum] AS eae
                    INNER JOIN [ifcSchema].[EnumItem] AS ei ON eae.TypeId = ei.TypeId AND eae.Value = ei.EnumItemId
                    WHERE eae.GlobalEntityInstanceId = ? AND eae.OrdinalPosition = 9;
                """
                cursor_main.execute(query_enum_9, target_id)
                row_enum_9 = cursor_main.fetchone()
                val_enum_9 = row_enum_9[0] if row_enum_9 else "Non definito"
                QTreeWidgetItem(attr_root, ["CompositionType", str(val_enum_9), ""])

                # Query Enum per PredefinedType (OrdinalPosition = 10)
                query_enum_10 = """
                    SELECT ei.EnumItemName FROM [ifcInstance].[EntityAttributeOfEnum] AS eae
                    INNER JOIN [ifcSchema].[EnumItem] AS ei ON eae.TypeId = ei.TypeId AND eae.Value = ei.EnumItemId
                    WHERE eae.GlobalEntityInstanceId = ? AND eae.OrdinalPosition = 10;
                """
                cursor_main.execute(query_enum_10, target_id)
                row_enum_10 = cursor_main.fetchone()
                val_enum_10 = row_enum_10[0] if row_enum_10 else "Non definito"
                QTreeWidgetItem(attr_root, ["PredefinedType", str(val_enum_10), ""])

            else:
                # --- PIPELINE STANDARD: IFCELEMENT ---
                query_string = """
                    SELECT OrdinalPosition, Value FROM [ifcInstance].[EntityAttributeOfString]
                    WHERE GlobalEntityInstanceId = ? ORDER BY OrdinalPosition;
                """
                cursor_main.execute(query_string, target_id)
                risultati_string = cursor_main.fetchall()
                mappatura_string = {1: "GlobalId", 3: "Name", 5: "ObjectType", 8: "Tag"}
                
                if risultati_string:
                    for row in risultati_string:
                        nome = mappatura_string.get(row[0], f"Altro (Posizione {row[0]})")
                        QTreeWidgetItem(attr_root, [nome, str(row[1]), ""])

                query_enum = """
                    SELECT ei.EnumItemName FROM [ifcInstance].[EntityAttributeOfEnum] AS eae
                    INNER JOIN [ifcSchema].[EnumItem] AS ei ON eae.TypeId = ei.TypeId AND eae.Value = ei.EnumItemId
                    WHERE eae.GlobalEntityInstanceId = ? AND eae.OrdinalPosition = 9;
                """
                cursor_main.execute(query_enum, target_id)
                row_enum = cursor_main.fetchone()
                val_enum = row_enum[0] if row_enum else "Non definito"
                QTreeWidgetItem(attr_root, ["PredefinedType", str(val_enum), ""])

            QgsMessageLog.logMessage(f"FASE ATTRIBUTI impiega: {time.time() - t_attributi:.3f} secondi", "IFC_Filtro", Qgis.Info)
            
            class_proj_root.setExpanded(True)
            attr_root.setExpanded(True)
            QApplication.processEvents()


            # =================================================================================
            # FASE 2: STRUTTURA SPAZIALE / LIVELLO
            # =================================================================================
            
            t_spatial = time.time()

            if ifc_class == "IfcSpace":
                # --- PIPELINE PARALLELA: IFCSPACE (Usa IfcRelAggregates) ---
                storey_query_space = """
                    SELECT storeyName.[Value] AS NomeLivello 
                    FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                    JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAggregates'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] spatialRef ON spatialRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND spatialRef.OrdinalPosition = 5
                    JOIN [ifcInstance].[Entity] storeyEntity ON storeyEntity.GlobalEntityInstanceId = spatialRef.[Value]
                    JOIN [ifcSchema].[Type] storeyType ON storeyEntity.EntityTypeId = storeyType.TypeId AND storeyType.ExpressName = 'IfcBuildingStorey'
                    JOIN [ifcInstance].[EntityAttributeOfString] storeyName ON storeyName.GlobalEntityInstanceId = spatialRef.[Value] AND storeyName.OrdinalPosition = 3
                    WHERE relListObj.[Value] = ?;
                """
                cursor_main.execute(storey_query_space, target_id)
                livello = cursor_main.fetchone()
                if livello and livello[0]:
                    spatial_root = QTreeWidgetItem(self.treeWidget, [self.tr("SPATIAL LOCATION"), "", ""])
                    QTreeWidgetItem(spatial_root, ["IfcBuildingStorey Name", str(livello[0]), ""])

            else:
                # --- PIPELINE STANDARD: IFCELEMENT (Usa IfcRelContainedInSpatialStructure) ---
                storey_query = """
                    SELECT storeyName.[Value] AS NomeLivello FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                    JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelContainedInSpatialStructure'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] spatialRef ON spatialRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND spatialRef.OrdinalPosition = 6
                    JOIN [ifcInstance].[Entity] storeyEntity ON storeyEntity.GlobalEntityInstanceId = spatialRef.[Value]
                    JOIN [ifcSchema].[Type] storeyType ON storeyEntity.EntityTypeId = storeyType.TypeId AND storeyType.ExpressName = 'IfcBuildingStorey'
                    JOIN [ifcInstance].[EntityAttributeOfString] storeyName ON storeyName.GlobalEntityInstanceId = spatialRef.[Value] AND storeyName.OrdinalPosition = 3
                    WHERE relListObj.[Value] = ?;
                """
                cursor_main.execute(storey_query, target_id)
                livello = cursor_main.fetchone()
                if livello and livello[0]:
                    spatial_root = QTreeWidgetItem(self.treeWidget, [self.tr("SPATIAL LOCATION"), "", ""])
                    QTreeWidgetItem(spatial_root, ["IfcBuildingStorey Name", str(livello[0]), ""])

            QgsMessageLog.logMessage(f"FASE SPATIALE impiega: {time.time() - t_spatial:.3f} secondi", "IFC_Filtro", Qgis.Info)
            QApplication.processEvents()

            # =================================================================================
            # FASE 3: APPARTENENZA A SISTEMI / GRUPPI (uguale per spazi ed elementi)
            # =================================================================================

            t_sistemi = time.time()

            system_query = """
                SELECT ISNULL(systemName.[Value], 'Senza Nome') AS NomeSistema, ISNULL(systemType.[Value], 'Senza Tipo') AS TipoSistema
                FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssignsToGroup'
                JOIN [ifcInstance].[EntityAttributeOfEntityRef] groupRef ON groupRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND groupRef.OrdinalPosition = 7
                LEFT JOIN [ifcInstance].[EntityAttributeOfString] systemName ON systemName.GlobalEntityInstanceId = groupRef.[Value] AND systemName.OrdinalPosition = 3
                LEFT JOIN [ifcInstance].[EntityAttributeOfString] systemType ON systemType.GlobalEntityInstanceId = groupRef.[Value] AND systemType.OrdinalPosition = 5
                WHERE relListObj.[Value] = ?;
            """
            cursor_main.execute(system_query, target_id)
            sistemi = cursor_main.fetchall()

            if sistemi:
                sys_root = QTreeWidgetItem(self.treeWidget, [self.tr("SYSTEMS AND GROUPS"), "", ""])
                for i, sis in enumerate(sistemi, 1):
                    sys_node = QTreeWidgetItem(sys_root, [f"Group/System {i}", "", ""])
                    QTreeWidgetItem(sys_node, ["Name", str(sis[0]), ""])
                    QTreeWidgetItem(sys_node, ["ObjectType", str(sis[1]), ""])

            QgsMessageLog.logMessage(f"FASE SISTEMI impiega: {time.time() - t_sistemi:.3f} secondi", "IFC_Filtro", Qgis.Info)
            QApplication.processEvents()

            # =================================================================================
            # FASE 4: MATERIALI ASSOCIATI (non si applica agli spazi)
            # =================================================================================
            
            t_materiali = time.time()
            
            if ifc_class != "IfcSpace":

                material_query = """
                    SELECT matName.Value AS MaterialName, ISNULL(matCat.Value, 'N/D') AS MaterialCategory, CAST(matThick.Value AS VARCHAR) AS Prop, 'IfcMaterialLayerSet' AS Tipo 
                    FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId 
                    JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                    JOIN [ifcInstance].[Entity] matSetEntity ON matSetEntity.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcSchema].[Type] matSetType ON matSetEntity.EntityTypeId = matSetType.TypeId AND matSetType.ExpressName = 'IfcMaterialLayerSet'
                    JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matLayerList ON matLayerList.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matLayerRef ON matLayerRef.GlobalEntityInstanceId = matLayerList.Value AND matLayerRef.OrdinalPosition = 1
                    JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matLayerRef.Value AND matName.OrdinalPosition = 1 
                    LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matLayerRef.Value AND matCat.OrdinalPosition = 3
                    JOIN [ifcInstance].[EntityAttributeOfFloat] matThick ON matThick.GlobalEntityInstanceId = matLayerList.Value AND matThick.OrdinalPosition = 2 WHERE relListObj.Value = ?
                    UNION ALL
                    SELECT matName.Value AS MaterialName, ISNULL(matCat.Value, 'N/D') AS MaterialCategory, 'N/D' AS Prop, 'IfcMaterialConstituentSet' AS Tipo 
                    FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId 
                    JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                    JOIN [ifcInstance].[Entity] matSetEntity ON matSetEntity.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcSchema].[Type] matSetType ON matSetEntity.EntityTypeId = matSetType.TypeId AND matSetType.ExpressName = 'IfcMaterialConstituentSet'
                    JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matConstList ON matConstList.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matConstRef ON matConstRef.GlobalEntityInstanceId = matConstList.Value AND matConstRef.OrdinalPosition = 3
                    JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matConstRef.Value AND matName.OrdinalPosition = 1 
                    LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matConstRef.Value AND matCat.OrdinalPosition = 3 WHERE relListObj.Value = ?
                    UNION ALL
                    SELECT matName.Value AS MaterialName, ISNULL(matCat.Value, 'N/D') AS MaterialCategory, 'N/D' AS Prop, 'IfcMaterial' AS Tipo 
                    FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId 
                    JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                    JOIN [ifcInstance].[Entity] matEntity ON matEntity.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcSchema].[Type] matType ON matEntity.EntityTypeId = matType.TypeId AND matType.ExpressName = 'IfcMaterial'
                    JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matRef.Value AND matName.OrdinalPosition = 1 
                    LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matRef.Value AND matCat.OrdinalPosition = 3 WHERE relListObj.Value = ?
                    UNION ALL
                    SELECT matName.Value AS MaterialName, ISNULL(matCat.Value, 'N/D') AS MaterialCategory, 'N/D' AS Prop, 'IfcMaterialProfileSet' AS Tipo 
                    FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId 
                    JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                    JOIN [ifcInstance].[Entity] matSetEntity ON matSetEntity.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcSchema].[Type] matSetType ON matSetEntity.EntityTypeId = matSetType.TypeId AND matSetType.ExpressName = 'IfcMaterialProfileSet'
                    JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matProfList ON matProfList.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matProfRef ON matProfRef.GlobalEntityInstanceId = matProfList.Value AND matProfRef.OrdinalPosition = 3
                    JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matProfRef.Value AND matName.OrdinalPosition = 1 
                    LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matProfRef.Value AND matCat.OrdinalPosition = 3 WHERE relListObj.Value = ?
                    UNION ALL
                    SELECT matName.Value AS MaterialName, ISNULL(matCat.Value, 'N/D') AS MaterialCategory, 'N/D' AS Prop, 'IfcMaterialList' AS Tipo 
                    FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId 
                    JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                    JOIN [ifcInstance].[Entity] matListEntity ON matListEntity.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcSchema].[Type] matListType ON matListEntity.EntityTypeId = matListType.TypeId AND matListType.ExpressName = 'IfcMaterialList'
                    JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matItemList ON matItemList.GlobalEntityInstanceId = matRef.Value 
                    JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matItemList.Value AND matName.OrdinalPosition = 1 
                    LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matItemList.Value AND matCat.OrdinalPosition = 3 WHERE relListObj.Value = ?
                """
                cursor_main.execute(material_query, target_id, target_id, target_id, target_id, target_id)
                materiali = cursor_main.fetchall()

                if materiali:
                    material_root = QTreeWidgetItem(self.treeWidget, [self.tr("MATERIALS"), "", ""])
                    for i, mat in enumerate(materiali, start=1):
                        mat_node = QTreeWidgetItem(material_root, [f"Material {i} ({mat[3]})", "", ""])
                        QTreeWidgetItem(mat_node, ["Name", str(mat[0]), ""])
                        QTreeWidgetItem(mat_node, ["Category", str(mat[1]), ""])
                        if 'LayerSet' in mat[3]: 
                            QTreeWidgetItem(mat_node, ["LayerThickness", str(mat[2])])
            
            QgsMessageLog.logMessage(f"FASE MATERIALI impiega: {time.time() - t_materiali:.3f} secondi", "IFC_Filtro", Qgis.Info)
            QApplication.processEvents()

            # =================================================================================
            # FASE 5: PROPERTY SETS (Uguale per spazi ed elementi)
            # =================================================================================

            t_pset = time.time()

            master_query_pset = """
                SELECT psetName.Value AS PsetName, propName.Value AS PropName, propRef.Value AS PropID
                FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relRef
                JOIN [ifcInstance].[Entity] e ON relRef.GlobalEntityInstanceId = e.GlobalEntityInstanceId
                JOIN [ifcSchema].[Type] t ON e.EntityTypeId = t.TypeId AND t.ExpressName = 'IfcRelDefinesByProperties'
                JOIN [ifcInstance].[EntityAttributeOfEntityRef] psetRef ON psetRef.GlobalEntityInstanceId = relRef.GlobalEntityInstanceId AND psetRef.OrdinalPosition = 6
                JOIN [ifcInstance].[EntityAttributeOfString] psetName ON psetName.GlobalEntityInstanceId = psetRef.Value AND psetName.OrdinalPosition = 3
                JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] propRef ON propRef.GlobalEntityInstanceId = psetRef.Value AND propRef.OrdinalPosition = 5
                JOIN [ifcInstance].[EntityAttributeOfString] propName ON propName.GlobalEntityInstanceId = propRef.Value AND propName.OrdinalPosition = 1
                WHERE relRef.Value = ?;
            """
            cursor_main.execute(master_query_pset, target_id)
            props_pset = cursor_main.fetchall()

            dynamic_value_query_pset = """
                SET NOCOUNT ON;
                DECLARE @PropID INT = ?;
                DECLARE @Result NVARCHAR(MAX) = NULL;
                DECLARE @ExpressName NVARCHAR(255) = NULL;
                DECLARE @TableName NVARCHAR(128);
                DECLARE @DynSQL NVARCHAR(MAX);
                DECLARE TableCursor CURSOR LOCAL FAST_FORWARD FOR
                SELECT t.name FROM sys.tables t INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                INNER JOIN sys.columns c1 ON t.object_id = c1.object_id AND c1.name = 'GlobalEntityInstanceId'
                INNER JOIN sys.columns c2 ON t.object_id = c2.object_id AND c2.name = 'OrdinalPosition'
                INNER JOIN sys.columns c3 ON t.object_id = c3.object_id AND c3.name = 'Value' WHERE s.name = 'ifcInstance';
                OPEN TableCursor; FETCH NEXT FROM TableCursor INTO @TableName;
                WHILE @@FETCH_STATUS = 0
                BEGIN
                    IF @TableName = 'EntityAttributeOfBoolean'
                    BEGIN
                        SET @DynSQL = N'SELECT @res = CASE WHEN t.ExpressName = ''IfcBoolean'' AND CAST(attr.Value AS INT) = 1 THEN ''True'' WHEN t.ExpressName = ''IfcBoolean'' AND CAST(attr.Value AS INT) = 0 THEN ''False'' ELSE CAST(attr.Value AS NVARCHAR(MAX)) END, @exp = t.ExpressName FROM [ifcInstance].[' + @TableName + '] attr LEFT JOIN [ifcSchema].[Type] t ON attr.TypeId = t.TypeId WHERE attr.GlobalEntityInstanceId = @pid AND attr.OrdinalPosition = 3;';
                    END
                    ELSE
                    BEGIN
                        SET @DynSQL = N'SELECT @res = CAST(attr.Value AS NVARCHAR(MAX)), @exp = t.ExpressName FROM [ifcInstance].[' + @TableName + '] attr LEFT JOIN [ifcSchema].[Type] t ON attr.TypeId = t.TypeId WHERE attr.GlobalEntityInstanceId = @pid AND attr.OrdinalPosition = 3;';
                    END
                    EXEC sp_executesql @DynSQL, N'@pid INT, @res NVARCHAR(MAX) OUTPUT, @exp NVARCHAR(255) OUTPUT', @pid = @PropID, @res = @Result OUTPUT, @exp = @ExpressName OUTPUT;
                    IF @Result IS NOT NULL BREAK;
                    FETCH NEXT FROM TableCursor INTO @TableName;
                END
                CLOSE TableCursor; DEALLOCATE TableCursor;
                SELECT @Result, @ExpressName;
            """

            if props_pset:  
                pset_root = QTreeWidgetItem(self.treeWidget, [self.tr("PROPERTY SETS"), "", ""])
                pset_nodes = {}
                for riga in props_pset:
                    pset_name, prop_name, prop_id = riga[0], riga[1], riga[2]
                    if pset_name not in pset_nodes: pset_nodes[pset_name] = QTreeWidgetItem(pset_root, [pset_name, "", ""])
                    
                    cursor_value.execute(dynamic_value_query_pset, prop_id)
                    valore_row = cursor_value.fetchone()
                    valore = "Vuoto"
                    expr_name = None
                    if valore_row:
                        valore = valore_row[0] if valore_row[0] is not None else "Vuoto"
                        expr_name = valore_row[1]
                    
                    unita_abbr = find_unit_abbr(expr_name, project_units_map)
                    QTreeWidgetItem(pset_nodes[pset_name], [prop_name, str(valore), unita_abbr])

            QgsMessageLog.logMessage(f"FASE PSET impiega: {time.time() - t_pset:.3f} secondi", "IFC_Filtro", Qgis.Info)
            QApplication.processEvents()

            # =================================================================================
            # FASE 6: QUANTITY TAKE-OFF (QTO) (uguale per spazi ed elementi)
            # =================================================================================

            t_QTO = time.time()

            master_query_qto = """
                SELECT psetName.Value AS PsetName, propName.Value AS PropName, propRef.Value AS PropID
                FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relRef
                JOIN [ifcInstance].[Entity] e ON relRef.GlobalEntityInstanceId = e.GlobalEntityInstanceId
                JOIN [ifcSchema].[Type] t ON e.EntityTypeId = t.TypeId AND t.ExpressName = 'IfcRelDefinesByProperties'
                JOIN [ifcInstance].[EntityAttributeOfEntityRef] psetRef ON psetRef.GlobalEntityInstanceId = relRef.GlobalEntityInstanceId AND psetRef.OrdinalPosition = 6
                JOIN [ifcInstance].[EntityAttributeOfString] psetName ON psetName.GlobalEntityInstanceId = psetRef.Value AND psetName.OrdinalPosition = 3
                JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] propRef ON propRef.GlobalEntityInstanceId = psetRef.Value AND propRef.OrdinalPosition = 6
                JOIN [ifcInstance].[EntityAttributeOfString] propName ON propName.GlobalEntityInstanceId = propRef.Value AND propName.OrdinalPosition = 1
                WHERE relRef.Value = ?;
            """
            cursor_main.execute(master_query_qto, target_id)
            props_qto = cursor_main.fetchall()

            dynamic_value_query_qto = """
                SET NOCOUNT ON;
                DECLARE @PropID INT = ?;
                DECLARE @Result NVARCHAR(MAX) = NULL;
                DECLARE @ExpressName NVARCHAR(255) = NULL;
                DECLARE @TableName NVARCHAR(128);
                DECLARE @DynSQL NVARCHAR(MAX);
                DECLARE TableCursor CURSOR LOCAL FAST_FORWARD FOR
                SELECT t.name FROM sys.tables t INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                INNER JOIN sys.columns c1 ON t.object_id = c1.object_id AND c1.name = 'GlobalEntityInstanceId'
                INNER JOIN sys.columns c2 ON t.object_id = c2.object_id AND c2.name = 'OrdinalPosition'
                INNER JOIN sys.columns c3 ON t.object_id = c3.object_id AND c3.name = 'Value' WHERE s.name = 'ifcInstance';
                OPEN TableCursor; FETCH NEXT FROM TableCursor INTO @TableName;
                WHILE @@FETCH_STATUS = 0
                BEGIN
                    IF @TableName = 'EntityAttributeOfBoolean'
                    BEGIN
                        SET @DynSQL = N'SELECT @res = CASE WHEN t.ExpressName = ''IfcBoolean'' AND CAST(attr.Value AS INT) = 1 THEN ''True'' WHEN t.ExpressName = ''IfcBoolean'' AND CAST(attr.Value AS INT) = 0 THEN ''False'' ELSE CAST(attr.Value AS NVARCHAR(MAX)) END, @exp = t.ExpressName FROM [ifcInstance].[' + @TableName + '] attr LEFT JOIN [ifcSchema].[Type] t ON attr.TypeId = t.TypeId WHERE attr.GlobalEntityInstanceId = @pid AND attr.OrdinalPosition = 4;';
                    END
                    ELSE
                    BEGIN
                        SET @DynSQL = N'SELECT @res = CAST(attr.Value AS NVARCHAR(MAX)), @exp = t.ExpressName FROM [ifcInstance].[' + @TableName + '] attr LEFT JOIN [ifcSchema].[Type] t ON attr.TypeId = t.TypeId WHERE attr.GlobalEntityInstanceId = @pid AND attr.OrdinalPosition = 4;';
                    END
                    EXEC sp_executesql @DynSQL, N'@pid INT, @res NVARCHAR(MAX) OUTPUT, @exp NVARCHAR(255) OUTPUT', @pid = @PropID, @res = @Result OUTPUT, @exp = @ExpressName OUTPUT;
                    IF @Result IS NOT NULL BREAK;
                    FETCH NEXT FROM TableCursor INTO @TableName;
                END
                CLOSE TableCursor; DEALLOCATE TableCursor;
                SELECT @Result, @ExpressName;
            """

            if props_qto:
                qto_root = QTreeWidgetItem(self.treeWidget, [self.tr("QUANTITY TAKE-OFF"), "", ""])
                qto_nodes = {}
                for riga in props_qto:
                    qto_name, prop_name, prop_id = riga[0], riga[1], riga[2]
                    if qto_name not in qto_nodes: qto_nodes[qto_name] = QTreeWidgetItem(qto_root, [qto_name, "", ""])
                    
                    cursor_value.execute(dynamic_value_query_qto, prop_id)
                    valore_row = cursor_value.fetchone()
                    valore = "Vuoto"
                    expr_name = None
                    if valore_row:
                        valore = valore_row[0] if valore_row[0] is not None else "Vuoto"
                        expr_name = valore_row[1]
                    
                    unita_abbr = find_unit_abbr(expr_name, project_units_map)
                    QTreeWidgetItem(qto_nodes[qto_name], [prop_name, str(valore), unita_abbr])

            QgsMessageLog.logMessage(f"FASE QTO impiega: {time.time() - t_QTO:.3f} secondi", "IFC_Filtro", Qgis.Info)
            QApplication.processEvents()

            # =================================================================================
            # MACRO-GRUPPO: INFORMAZIONI DI TIPO (FASI 7, 8, 9 UNITE)
            # =================================================================================
            # Creiamo prima il menu principale "TIPO" nell'albero
            type_main_root = None

            # =================================================================================
            # FASE 7: ATTRIBUTI DEL TIPO (ELEMENT TYPE) -> Diventa figlio di type_main_root
            # =================================================================================
            
            t_TYPE = time.time()

            type_attributes_query = """
                SELECT 
                    typeRef.Value AS ElementTypeId,
                    typeGlobalId.Value AS TypeGlobalId,
                    tType.ExpressName AS ClassName,
                    typeName.Value AS TypeName,
                    typeTag.Value AS TypeTag,
                    enumDef.EnumItemName AS PredefinedType
                FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                JOIN [ifcInstance].[Entity] e ON e.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                JOIN [ifcSchema].[Type] t ON e.EntityTypeId = t.TypeId AND t.ExpressName = 'IfcRelDefinesByType'
                JOIN [ifcInstance].[EntityAttributeOfEntityRef] typeRef ON typeRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND typeRef.OrdinalPosition = 6
                JOIN [ifcInstance].[Entity] eType ON eType.GlobalEntityInstanceId = typeRef.Value
                JOIN [ifcSchema].[Type] tType ON tType.TypeId = eType.EntityTypeId
                LEFT JOIN [ifcInstance].[EntityAttributeOfString] typeGlobalId ON typeGlobalId.GlobalEntityInstanceId = typeRef.Value AND typeGlobalId.OrdinalPosition = 1
                LEFT JOIN [ifcInstance].[EntityAttributeOfString] typeName ON typeName.GlobalEntityInstanceId = typeRef.Value AND typeName.OrdinalPosition = 3
                LEFT JOIN [ifcInstance].[EntityAttributeOfString] typeTag ON typeTag.GlobalEntityInstanceId = typeRef.Value AND typeTag.OrdinalPosition = 8
                LEFT JOIN [ifcInstance].[EntityAttributeOfEnum] typeEnum ON typeEnum.GlobalEntityInstanceId = typeRef.Value
                LEFT JOIN [ifcSchema].[EnumItem] enumDef ON enumDef.TypeId = typeEnum.TypeId AND enumDef.EnumItemId = typeEnum.Value
                WHERE relListObj.Value = ?;
            """
            cursor_main.execute(type_attributes_query, target_id)
            type_attr_row = cursor_main.fetchone()
            
            element_type_id = None
            if type_attr_row:
                element_type_id = str(type_attr_row[0])

                # Creazione del macro-gruppo
                if type_main_root is None:
                    type_main_root = QTreeWidgetItem(self.treeWidget, [self.tr("TYPE"), "", ""])

                type_attr_root = QTreeWidgetItem(type_main_root, [self.tr("TYPE ATTRIBUTES"), "", ""])

                QTreeWidgetItem(type_attr_root, ["GlobalId", str(type_attr_row[1]) if type_attr_row[1] else "Non definito", ""])
                QTreeWidgetItem(type_attr_root, ["IFC Class", str(type_attr_row[2]), ""])
                QTreeWidgetItem(type_attr_root, ["Name", str(type_attr_row[3]) if type_attr_row[3] else "Non definito", ""])
                QTreeWidgetItem(type_attr_root, ["Tag", str(type_attr_row[4]) if type_attr_row[4] else "Non definito", ""])
                QTreeWidgetItem(type_attr_root, ["PredefinedType", str(type_attr_row[5]) if type_attr_row[5] else "Non definito", ""])


            # =================================================================================
            # FASE 8: PROPERTY SET DI TIPO (TYPE PSET) -> Diventa figlio di type_main_root
            # =================================================================================
            
           
            if element_type_id:
                type_master_query_pset = """
                    SELECT psetName.Value AS PsetName, propName.Value AS PropName, propRef.Value AS PropID FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                    JOIN [ifcInstance].[Entity] e ON relListObj.GlobalEntityInstanceId = e.GlobalEntityInstanceId
                    JOIN [ifcSchema].[Type] t ON e.EntityTypeId = t.TypeId AND t.ExpressName = 'IfcRelDefinesByType'
                    JOIN [ifcInstance].[EntityAttributeOfEntityRef] typeRef ON typeRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND typeRef.OrdinalPosition = 6
                    JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] psetList ON psetList.GlobalEntityInstanceId = typeRef.Value AND psetList.OrdinalPosition = 6
                    JOIN [ifcInstance].[EntityAttributeOfString] psetName ON psetName.GlobalEntityInstanceId = psetList.Value AND psetName.OrdinalPosition = 3
                    JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] propRef ON propRef.GlobalEntityInstanceId = psetList.Value AND propRef.OrdinalPosition = 5
                    JOIN [ifcInstance].[EntityAttributeOfString] propName ON propName.GlobalEntityInstanceId = propRef.Value AND propName.OrdinalPosition = 1
                    WHERE relListObj.Value = ?;
                """
                
                cursor_main.execute(type_master_query_pset, target_id)
                type_props_pset = cursor_main.fetchall()
                
                if type_props_pset:
                    if type_main_root is None: type_main_root = QTreeWidgetItem(self.treeWidget, [self.tr("TYPE"), "", ""])
                    type_pset_root = QTreeWidgetItem(type_main_root, [self.tr("TYPE PROPERTY SETS"), "", ""])
                    type_pset_nodes = {}
                    for riga in type_props_pset:
                        pset_name, prop_name, prop_id = riga[0], riga[1], riga[2]
                        if pset_name not in type_pset_nodes: type_pset_nodes[pset_name] = QTreeWidgetItem(type_pset_root, [pset_name, "", ""])
                        
                        cursor_value.execute(dynamic_value_query_pset, prop_id)
                        valore_row = cursor_value.fetchone()
                        valore = "Vuoto"
                        expr_name = None
                        if valore_row:
                            valore = valore_row[0] if valore_row[0] is not None else "Vuoto"
                            expr_name = valore_row[1]
                        
                        unita_abbr = find_unit_abbr(expr_name, project_units_map)
                        QTreeWidgetItem(type_pset_nodes[pset_name], [prop_name, str(valore), unita_abbr])
            

            # =================================================================================
            # FASE 9: MATERIALI DEL TIPO (TYPE MATERIALS) -> Diventa figlio di type_main_root
            # =================================================================================
            if ifc_class != "IfcSpace":
                
                if element_type_id:
                    type_material_query = """
                        -- CASO 1: IfcMaterialLayerSet
                        SELECT 
                            matName.Value AS MaterialName,
                            ISNULL(matCat.Value, 'N/D') AS MaterialCategory,
                            CAST(matThick.Value AS VARCHAR) AS ProprietaAggiuntiva,
                            'IfcMaterialLayerSet' AS TipoAssegnazione
                        FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                        JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                        JOIN [ifcInstance].[Entity] matSetEntity ON matSetEntity.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcSchema].[Type] matSetType ON matSetEntity.EntityTypeId = matSetType.TypeId AND matSetType.ExpressName = 'IfcMaterialLayerSet'
                        JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matLayerList ON matLayerList.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matLayerRef ON matLayerRef.GlobalEntityInstanceId = matLayerList.Value AND matLayerRef.OrdinalPosition = 1
                        JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matLayerRef.Value AND matName.OrdinalPosition = 1
                        LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matLayerRef.Value AND matCat.OrdinalPosition = 3
                        JOIN [ifcInstance].[EntityAttributeOfFloat] matThick ON matThick.GlobalEntityInstanceId = matLayerList.Value AND matThick.OrdinalPosition = 2
                        WHERE relListObj.Value = ?

                        UNION ALL

                        -- CASO 2: IfcMaterialConstituentSet
                        SELECT 
                            matName.Value AS MaterialName,
                            ISNULL(matCat.Value, 'N/D') AS MaterialCategory,
                            'N/D' AS ProprietaAggiuntiva,
                            'IfcMaterialConstituentSet' AS TipoAssegnazione
                        FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                        JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                        JOIN [ifcInstance].[Entity] matSetEntity ON matSetEntity.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcSchema].[Type] matSetType ON matSetEntity.EntityTypeId = matSetType.TypeId AND matSetType.ExpressName = 'IfcMaterialConstituentSet'
                        JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matConstList ON matConstList.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matConstRef ON matConstRef.GlobalEntityInstanceId = matConstList.Value AND matConstRef.OrdinalPosition = 3
                        JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matConstRef.Value AND matName.OrdinalPosition = 1
                        LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matConstRef.Value AND matCat.OrdinalPosition = 3
                        WHERE relListObj.Value = ?

                        UNION ALL

                        -- CASO 3: IfcMaterial
                        SELECT 
                            matName.Value AS MaterialName,
                            ISNULL(matCat.Value, 'N/D') AS MaterialCategory,
                            'N/D' AS ProprietaAggiuntiva,
                            'IfcMaterial' AS TipoAssegnazione
                        FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                        JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                        JOIN [ifcInstance].[Entity] matEntity ON matEntity.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcSchema].[Type] matType ON matEntity.EntityTypeId = matType.TypeId AND matType.ExpressName = 'IfcMaterial'
                        JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matRef.Value AND matName.OrdinalPosition = 1
                        LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matRef.Value AND matCat.OrdinalPosition = 3
                        WHERE relListObj.Value = ?

                        UNION ALL

                        -- CASO 4: IfcMaterialProfileSet
                        SELECT 
                            matName.Value AS MaterialName,
                            ISNULL(matCat.Value, 'N/D') AS MaterialCategory,
                            'N/D' AS ProprietaAggiuntiva,
                            'IfcMaterialProfileSet' AS TipoAssegnazione
                        FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                        JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                        JOIN [ifcInstance].[Entity] matSetEntity ON matSetEntity.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcSchema].[Type] matSetType ON matSetEntity.EntityTypeId = matSetType.TypeId AND matSetType.ExpressName = 'IfcMaterialProfileSet'
                        JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matProfList ON matProfList.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matProfRef ON matProfRef.GlobalEntityInstanceId = matProfList.Value AND matProfRef.OrdinalPosition = 3
                        JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matProfRef.Value AND matName.OrdinalPosition = 1
                        LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matProfRef.Value AND matCat.OrdinalPosition = 3
                        WHERE relListObj.Value = ?

                        UNION ALL

                        -- CASO 5: IfcMaterialList
                        SELECT 
                            matName.Value AS MaterialName,
                            ISNULL(matCat.Value, 'N/D') AS MaterialCategory,
                            'N/D' AS ProprietaAggiuntiva,
                            'IfcMaterialList' AS TipoAssegnazione
                        FROM [ifcInstance].[EntityAttributeListElementOfEntityRef] relListObj
                        JOIN [ifcInstance].[Entity] relEntity ON relEntity.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId
                        JOIN [ifcSchema].[Type] relType ON relEntity.EntityTypeId = relType.TypeId AND relType.ExpressName = 'IfcRelAssociatesMaterial'
                        JOIN [ifcInstance].[EntityAttributeOfEntityRef] matRef ON matRef.GlobalEntityInstanceId = relListObj.GlobalEntityInstanceId AND matRef.OrdinalPosition = 6
                        JOIN [ifcInstance].[Entity] matListEntity ON matListEntity.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcSchema].[Type] matListType ON matListEntity.EntityTypeId = matListType.TypeId AND matListType.ExpressName = 'IfcMaterialList'
                        JOIN [ifcInstance].[EntityAttributeListElementOfEntityRef] matItemList ON matItemList.GlobalEntityInstanceId = matRef.Value
                        JOIN [ifcInstance].[EntityAttributeOfString] matName ON matName.GlobalEntityInstanceId = matItemList.Value AND matName.OrdinalPosition = 1
                        LEFT JOIN [ifcInstance].[EntityAttributeOfString] matCat ON matCat.GlobalEntityInstanceId = matItemList.Value AND matCat.OrdinalPosition = 3
                        WHERE relListObj.Value = ?;
                    """
                    cursor_main.execute(type_material_query, element_type_id, element_type_id, element_type_id, element_type_id, element_type_id)
                    type_materiali_trovati = cursor_main.fetchall()
                    
                    if type_materiali_trovati:
                        if type_main_root is None:
                            type_main_root = QTreeWidgetItem(self.treeWidget, [self.tr("TYPE"), "", ""])
                        
                        type_material_root = QTreeWidgetItem(type_main_root, [self.tr("TYPE MATERIALS"), "", ""])
                        for i, mat in enumerate(type_materiali_trovati, start=1):
                            mat_node = QTreeWidgetItem(type_material_root, [f"Material {i} ({mat[3]})", "", ""])
                            QTreeWidgetItem(mat_node, ["Name", str(mat[0]), ""])
                            QTreeWidgetItem(mat_node, ["Category", str(mat[1]), ""])
                            if 'LayerSet' in mat[3]: 
                                QTreeWidgetItem(mat_node, ["LayerThickness", str(mat[2])])

            QgsMessageLog.logMessage(f"FASE TYPE impiega: {time.time() - t_TYPE:.3f} secondi", "IFC_Filtro", Qgis.Info)
            QgsMessageLog.logMessage(f"=== TEMPO TOTALE INTERROGAZIONE: {time.time() - t_inizio:.3f} secondi ===", "IFC_Filtro", Qgis.Info)
            QApplication.processEvents()

            header = self.treeWidget.header()
            # DISATTIVA il vincolo di Qt che costringe l'ultima colonna a riempire il pannello
            header.setStretchLastSection(False)

            # (Proprietà): Prende solo lo spazio che serve al testo
            header.setSectionResizeMode(1, QHeaderView.Stretch) 
            # (Valore): Si allunga/stringe dinamicamente occupando tutto lo spazio rimasto
            header.setSectionResizeMode(0, QHeaderView.Stretch)          
            # (Unità): Prende lo spazio necessario e resta agganciata al bordo destro
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

            conn.close()
            
        except Exception as e:
            # Sblocca il cursore se era rimasto in attesa
            QApplication.restoreOverrideCursor()
            
            # Costruisce il messaggio dettagliato per l'utente
            msg_errore = self.tr(
                "Errore durante l'interrogazione dell'oggetto:\n{error}\n\n"
                "ATTENZIONE: L'operazione è stata interrotta. I dati caricati finora "
                "nell'albero potrebbero essere incompleti o parziali."
            ).format(error=str(e))

            QMessageBox.critical(self, self.tr("Errore Database"), msg_errore)
        finally:
            self._query_in_corso = False
            


















#class per la gestione della selezione degli elementi sulla mappa 

class IFCSelectionTool(QgsMapTool):
    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog
        self.setCursor(Qt.CrossCursor) # Cursore a mirino

    def canvasReleaseEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(self.canvas.window(), self.tr("Attenzione"), 
                                self.tr("Seleziona un layer vettoriale valido nel pannello dei layer prima di cliccare."))
            self.canvas.unsetMapTool(self) 
            return

        # Trasforma il clic in coordinate mappa
        point = self.toMapCoordinates(event.pos())
        
        # Area di tolleranza iniziale (5 pixel attorno al clic)
        search_radius = self.canvas.mapUnitsPerPixel() * 5
        search_rect = QgsRectangle(
            point.x() - search_radius, point.y() - search_radius,
            point.x() + search_radius, point.y() + search_radius
        )
        
        # 1. Recupera i candidati i cui Bounding Box intersecano il clic
        request = QgsFeatureRequest().setFilterRect(search_rect)
        features = list(layer.getFeatures(request))
        
        # Se non trova nessuna feature nel rettangolo di ricerca, avvisa l'utente
        if not features:
            QMessageBox.warning(self.canvas.window(), self.tr("Selezione vuota"), 
                                self.tr("Nessun elemento trovato nel punto cliccato.\n\nClicca su un oggetto IFC valido o cambia il layer di selezione."))
            self.canvas.unsetMapTool(self)
            return
        
        # 2. STRATEGIA DI SELEZIONE CHIRURGICA:
        # Creiamo un punto geometrico reale dal clic dell'utente
        click_geom = QgsGeometry.fromPointXY(point)
        
        target_feature = None
        min_distance = float('inf')
        
        # Cicliamo tra gli elementi vicini per trovare quello geometricamente più vicino
        for feature in features:
            if not feature.hasGeometry():
                continue
            
            # Calcola la distanza reale tra il clic e la geometria (muro, porta, pilastro, ecc.)
            dist = feature.geometry().distance(click_geom)
            
            if dist < min_distance:
                min_distance = dist
                target_feature = feature
        
        # Se l'elemento più vicino è comunque fuori dalla tolleranza dei 5 pixel, avvisa l'utente
        if target_feature is None or min_distance > search_radius:
            QMessageBox.warning(self.canvas.window(), self.tr("Selezione non valida"), 
                                self.tr("Il punto cliccato è troppo lontano dagli oggetti del layer.\n\nAvvicinati ad un elemento valido."))
            self.canvas.unsetMapTool(self)
            return

        
        # SELEZIONE E REPAINT IMMEDIATO
        
        # PULIZIA GLOBALE: Rimuove la selezione da TUTTI i layer del progetto
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                lyr.removeSelection()

        # Selezioniamo subito l'elemento e forziamo la GUI a processare l'evento grafico.
        # In questo modo si colorerà di giallo ISTANTANEAMENTE, anche se le query successive falliscono.
        layer.selectByIds([target_feature.id()])
        layer.triggerRepaint()
        QApplication.processEvents() 

        # 3. Controllo colonna sull'elemento più vicino isolato
        attr_idx = layer.fields().indexOf("GlobalId_MSSQL")
        if attr_idx == -1:
            QMessageBox.warning(self.canvas.window(), self.tr("Errore Layer"), 
                                self.tr("La colonna 'GlobalId_MSSQL' non è presente in questo layer."))
            self.canvas.unsetMapTool(self)
            return
            
        target_id = target_feature.attribute("GlobalId_MSSQL")
        if target_id is None or target_id == NULL or str(target_id).strip() == "":
            QMessageBox.warning(self.canvas.window(), self.tr("Valore mancante"), 
                                self.tr("L'elemento selezionato non ha un ID valido nella colonna 'GlobalId_MSSQL'."))
            self.canvas.unsetMapTool(self)
            return
            
        # Rimuove lo strumento dal canvas (scatta deactivate())
        self.canvas.unsetMapTool(self)
        
        # Avvia l'interrogazione nel database in sicurezza
        try:
            if self.dialog:
                self.dialog.execute_report_query(str(target_id), layer)
        except RuntimeError:
            pass 

    def deactivate(self):
        """Metodo nativo di QGIS: si attiva quando il tool viene rimosso."""
        try:
            if self.dialog:
                self.dialog.show()
        except RuntimeError:
            pass
        super().deactivate()
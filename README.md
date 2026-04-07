# <img src="https://github.com/MicheleBerlato/ifcSQL_Tools_for_QGIS/raw/main/Icons/icon.png" width="40" alt="icon"> ifcSQL_Tools_for_QGIS 
This repository contains the code for the ifcSQL_Tools QGIS plugin that allows you to interact with (load, view, filter, and delete) IFC data stored in the ifcSQL database system. 
You can upload all your georeferenced IFC files to the ifcSQL database and view them directly in the QGIS GUI in 2D or 3D. Below is an example of a wastewater treatment plant. <br><br>

<p align="center"> <img src="github_images/00_WWTP_IFC.png" alt="Screenshot ZIP download" /> </p>

![Screenshot ZIP download](github_images/01_WWTP_QGIS.png) <br><br><br><br>

# How to install and set up the plugin? 

(1) Download the ZIP file.
<br><br> ![Screenshot ZIP download](github_images/02_ZIP_download.png) <br><br>

(2) Install the plugin from the ZIP in QGIS. 
<br><br> ![Screenshot install plugin from ZIP](github_images/03_Install_from_ZIP.png) <br><br>

(3) Open the plugin folder, then open the “first_installation” folder and follow the instructions starting with the first PDF file: 0.Start with ifcSQL_Tools.
<br><br> ![GIF plugin folder](github_images/04_open_plugin_folder.gif) <br><br>

# How to use the plugin?

(0) Before you start using the plugin, you need to connect the two databases (MSSQL and PostgreSQL) that you created in the previous steps.
<br><br> ![GIF plugin folder](github_images/05.1_Connect_mssql.png) <br><br>
<br><br> ![GIF plugin folder](github_images/05.1_Connect_postgres.png) <br><br>

(1) You can import an IFC file using the “Import IFC file” button. Remember that you must import the file first into MSSQL and then into PostgreSQL for the process to be complete. The steps to follow (for both databases) are:
- Select an existing connection or create a new one.
- Connect to the selected database.
- Select the IFC file you want to import (for import into PostgreSQL, the plugin will suggest the last file imported into MSSQL).
- Import the IFC file.


(2) You can delete an IFC file using the “Delete IFC file” button. The file will be deleted from both databases or only from MSSQL if it has not been imported into PostgreSQL. The steps to follow are:
- Select the existing connections (both databases).
- Connect to the selected databases.
- Select the IFC file you want to delete (it will indicate whether the file is present only in MSSQL or in both databases).
- Delete the IFC file.


(3)You can query IFC geometries using the “IFC Query” button. You can filter the IFC geometries in your database by following these steps:
- Select an existing connection.
- Connect to the database.
- Decide whether to use both the context filter and the IFC filter (you can disable one of them).
- In the context filter, you can use three types of filters: “default filter” if you have areas loaded in your database; “manual filter” if you want to draw the area; “project filter” if you want to filter by a specific IFC file.
- In the IFC filter, you can select which IFC class or classes to filter by.
- Apply filter.



